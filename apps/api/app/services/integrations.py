"""Custom REST integrations: CRUD, cURL import, secret references, testing, tool sync."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.adapters.tools_http import HttpApiExecutor
from app.core.authz import AuthContext
from app.core.config import Settings
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.ssrf import OutboundBlocked, validate_outbound_url
from app.domain.curl_parser import CurlParseError, parse_curl, redact_curl
from app.domain.slugs import slugify
from app.domain.templates import input_schema_for, secrets_in, variables_in
from app.models.agents import Agent, AgentToolBinding, AgentVersion
from app.models.integrations import CustomIntegration, IntegrationSecret
from app.models.tools import Tool
from app.ports.secrets import SecretStore, key_preview
from app.schemas.admin import ToolCreate, ToolUpdate
from app.schemas.integrations import (
    CurlPreview,
    IntegrationCreate,
    IntegrationSecretIn,
    IntegrationTestOut,
    IntegrationUpdate,
)
from app.services import audit
from app.services.tools import ToolService

TEMPLATE_FIELDS = ("endpoint", "headers_template", "query_template", "body_template")


def _templates(i: CustomIntegration) -> list[str | None]:
    return [i.endpoint, *i.headers_template.values(), *i.query_template.values(), i.body_template]


def variables_of(i: CustomIntegration) -> list[str]:
    return variables_in(*_templates(i))


def missing_secrets_of(i: CustomIntegration) -> list[str]:
    have = {s.name for s in i.secrets}
    return [s for s in secrets_in(*_templates(i)) if s not in have]


def _snapshot(i: CustomIntegration) -> dict[str, Any]:
    return {
        "name": i.name,
        "method": i.method,
        "endpoint": i.endpoint,
        "headers": sorted(i.headers_template),
        "status": i.status,
        "timeout_seconds": i.timeout_seconds,
        "tool_id": str(i.tool_id) if i.tool_id else None,
    }


class IntegrationService:
    def __init__(self, session: AsyncSession, ctx: AuthContext, settings: Settings) -> None:
        self.session = session
        self.ctx = ctx
        self.settings = settings
        self.org_id = ctx.require_organization()

    async def _audit(
        self, action: str, entity_id: uuid.UUID, before: dict | None = None, after: dict | None = None
    ) -> None:
        await audit.record(
            self.session,
            action=action,
            entity_type="custom_integration",
            entity_id=entity_id,
            organization_id=self.org_id,
            actor_user_id=self.ctx.user_id,
            before=before,
            after=after,
            request_id=self.ctx.request_id,
            ip_address=self.ctx.ip_address,
        )

    def _query(self) -> Select[tuple[CustomIntegration]]:
        return (
            select(CustomIntegration)
            .options(selectinload(CustomIntegration.secrets))
            .where(CustomIntegration.organization_id == self.org_id)
        )

    async def list_all(self) -> Sequence[CustomIntegration]:
        return list((await self.session.scalars(self._query().order_by(CustomIntegration.name))).all())

    async def get(self, integration_id: uuid.UUID) -> CustomIntegration:
        row = await self.session.scalar(
            self._query()
            .where(CustomIntegration.id == integration_id)
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise NotFound("Integration not found", code="integration_not_found")
        return row

    async def used_by(self, integration_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        """Agents whose active version binds the integration's tool."""
        if not integration_ids:
            return {}
        rows = (
            await self.session.execute(
                select(CustomIntegration.id, Agent.name)
                .join(Tool, Tool.id == CustomIntegration.tool_id)
                .join(AgentToolBinding, AgentToolBinding.tool_id == Tool.id)
                .join(AgentVersion, AgentVersion.id == AgentToolBinding.agent_version_id)
                .join(Agent, Agent.id == AgentVersion.agent_id)
                .where(
                    CustomIntegration.id.in_(integration_ids),
                    Agent.active_version_id == AgentVersion.id,
                    AgentToolBinding.enabled.is_(True),
                )
            )
        ).all()
        out: dict[uuid.UUID, list[str]] = {}
        for iid, name in rows:
            out.setdefault(iid, []).append(name)
        return {k: sorted(v) for k, v in out.items()}

    async def tool_slugs(self, integrations: Sequence[CustomIntegration]) -> dict[uuid.UUID, str]:
        ids = [i.tool_id for i in integrations if i.tool_id]
        if not ids:
            return {}
        rows = (await self.session.execute(select(Tool.id, Tool.slug).where(Tool.id.in_(ids)))).all()
        return {tid: slug for tid, slug in rows}

    # ------------------------------------------------------------------ create / update
    def _validate_endpoint(self, endpoint: str) -> None:
        # placeholders may appear in the path: validate the static host now, the rendered URL at call time
        probe = endpoint
        for name in variables_in(endpoint):
            probe = probe.replace("{{" + name + "}}", "x")
        try:
            validate_outbound_url(probe, self.settings)
        except OutboundBlocked as exc:
            raise ValidationFailed(str(exc), code="outbound_blocked") from exc

    async def create(
        self, data: IntegrationCreate, secrets: SecretStore, *, raw_curl: str | None = None
    ) -> CustomIntegration:
        slug = data.slug or slugify(data.name)
        if await self.session.scalar(
            select(CustomIntegration.id).where(
                CustomIntegration.organization_id == self.org_id, CustomIntegration.slug == slug
            )
        ):
            raise Conflict(f"Integration slug '{slug}' already exists", code="slug_taken")
        self._validate_endpoint(data.endpoint)
        row = CustomIntegration(
            organization_id=self.org_id,
            name=data.name,
            slug=slug,
            description=data.description,
            method=data.method,
            endpoint=data.endpoint,
            headers_template=data.headers_template,
            query_template=data.query_template,
            body_template=data.body_template,
            content_type=data.content_type,
            timeout_seconds=data.timeout_seconds,
            max_response_bytes=data.max_response_bytes,
            created_by=self.ctx.user_id,
            updated_by=self.ctx.user_id,
            secrets=[],  # initialise the collection so no lazy load is needed before the first flush
        )
        self.session.add(row)
        await self.session.flush()
        for s in data.secrets:
            await self._store_secret(row, s, secrets)
        row.auth_summary = self._auth_summary(row)
        if data.create_tool:
            await self.sync_tool(row)
        await self.session.flush()
        await self._audit(
            "integration.created",
            row.id,
            after={
                **_snapshot(row),
                "secrets": [s.name for s in data.secrets],
                "imported_from_curl": raw_curl is not None,
            },
        )
        return await self.get(row.id)

    async def update(self, integration_id: uuid.UUID, data: IntegrationUpdate) -> CustomIntegration:
        row = await self.get(integration_id)
        before = _snapshot(row)
        changes = data.model_dump(exclude_unset=True)
        if "endpoint" in changes and changes["endpoint"]:
            self._validate_endpoint(changes["endpoint"])
        for k, v in changes.items():
            if v is not None or k == "body_template":
                setattr(row, k, v)
        row.auth_summary = self._auth_summary(row)
        row.updated_by = self.ctx.user_id
        await self.session.flush()
        if row.tool_id:
            await self.sync_tool(row)
        await self._audit("integration.updated", row.id, before=before, after=_snapshot(row))
        return await self.get(row.id)

    async def delete(self, integration_id: uuid.UUID, secrets: SecretStore) -> None:
        row = await self.get(integration_id)
        users = await self.used_by([row.id])
        if users.get(row.id):
            raise Conflict(
                f"Integration is used by agents: {', '.join(users[row.id])}. Remove the tool first.",
                code="integration_in_use",
                details=users[row.id],
            )
        snapshot = _snapshot(row)
        # ciphertext first (own transaction; DB cascade removes integration_secrets), then the ORM rows
        for secret in list(row.secrets):
            await secrets.delete(str(secret.secret_ref_id))
            self.session.expunge(secret)
        self.session.expire(row, ["secrets"])
        row = await self.get(row.id)
        if row.tool_id:
            tool = await self.session.get(Tool, row.tool_id)
            if tool is not None:
                await self.session.delete(tool)
        await self.session.delete(row)
        await self.session.flush()
        await self._audit("integration.deleted", integration_id, before=snapshot)

    # ------------------------------------------------------------------ secrets
    @staticmethod
    def _auth_summary(row: CustomIntegration) -> str:
        if not row.secrets:
            return "none"
        locs = {s.location for s in row.secrets}
        for loc in ("header", "basic", "query", "cookie", "body"):
            if loc in locs:
                return loc
        return "header"

    async def _store_secret(
        self, row: CustomIntegration, data: IntegrationSecretIn, secrets: SecretStore
    ) -> IntegrationSecret:
        existing = next((s for s in row.secrets if s.name == data.name), None)
        if existing is not None:
            handle = await secrets.rotate(str(existing.secret_ref_id), data.value)
            existing.fingerprint = handle.fingerprint
            existing.key_preview = key_preview(data.value)
            existing.location = data.location
            existing.rotated_at = datetime.now(UTC)
            return existing
        handle = await secrets.store(f"integration:{row.slug}:{data.name}", data.value)
        secret = IntegrationSecret(
            integration_id=row.id,
            name=data.name,
            secret_ref_id=uuid.UUID(handle.ref),
            fingerprint=handle.fingerprint,
            key_preview=key_preview(data.value),
            location=data.location,
        )
        self.session.add(secret)
        row.secrets.append(secret)
        return secret

    async def set_secret(
        self, integration_id: uuid.UUID, data: IntegrationSecretIn, secrets: SecretStore
    ) -> CustomIntegration:
        row = await self.get(integration_id)
        await self._store_secret(row, data, secrets)
        row.auth_summary = self._auth_summary(row)
        row.health_status = "unknown"
        await self.session.flush()
        await self._audit(
            "integration.secret_set", row.id, after={"name": data.name, "location": data.location}
        )
        return await self.get(row.id)

    async def delete_secret(
        self, integration_id: uuid.UUID, name: str, secrets: SecretStore
    ) -> CustomIntegration:
        row = await self.get(integration_id)
        secret = next((s for s in row.secrets if s.name == name), None)
        if secret is None:
            raise NotFound("Secret not found", code="secret_not_found")
        # The secret store commits in its own transaction; deleting secret_refs cascades to this
        # integration_secrets row at the database level, so the ORM must not issue its own DELETE
        # (that would hold a row lock the cascade waits on). Drop the ciphertext, then forget the
        # stale ORM object and reload the collection.
        await secrets.delete(str(secret.secret_ref_id))
        self.session.expunge(secret)
        self.session.expire(row, ["secrets"])
        row = await self.get(row.id)
        row.auth_summary = self._auth_summary(row)
        await self.session.flush()
        await self._audit("integration.secret_deleted", row.id, before={"name": name})
        return await self.get(row.id)

    # ------------------------------------------------------------------ cURL
    @staticmethod
    def preview_curl(text: str) -> CurlPreview:
        try:
            parsed = parse_curl(text)
        except CurlParseError as exc:
            raise ValidationFailed(str(exc), code="curl_parse_failed") from exc
        return CurlPreview(
            method=parsed.method,
            url=parsed.url,
            headers=parsed.headers,
            query=parsed.query,
            body=parsed.body,
            content_type=parsed.content_type,
            body_kind=parsed.body_kind,
            secrets=[
                {"name": s.name, "location": s.location, "hint": s.hint, "preview": key_preview(s.value)}
                for s in parsed.secrets
            ],
            variables=variables_in(parsed.url, *parsed.headers.values(), *parsed.query.values(), parsed.body),
            warnings=parsed.warnings,
            summary=parsed.summary(),
        )

    async def import_curl(
        self, *, name: str, description: str, curl: str, create_tool: bool, secrets: SecretStore
    ) -> CustomIntegration:
        try:
            parsed = parse_curl(curl)
        except CurlParseError as exc:
            raise ValidationFailed(str(exc), code="curl_parse_failed") from exc
        # the same secret name may appear in several places; the first value wins
        seen: dict[str, IntegrationSecretIn] = {}
        for s in parsed.secrets:
            seen.setdefault(s.name, IntegrationSecretIn(name=s.name, value=s.value, location=s.location))
        data = IntegrationCreate(
            name=name,
            description=description,
            method=parsed.method,
            endpoint=parsed.url,
            headers_template=parsed.headers,
            query_template=parsed.query,
            body_template=parsed.body,
            content_type=parsed.content_type,
            secrets=list(seen.values()),
            create_tool=create_tool,
        )
        row = await self.create(data, secrets, raw_curl=redact_curl(curl, parsed.secrets))
        return row

    # ------------------------------------------------------------------ tool sync (Agent → Tools → API)
    async def sync_tool(self, row: CustomIntegration) -> Tool:
        svc = ToolService(self.session, self.ctx)
        variables = variables_of(row)
        schema = input_schema_for(variables)
        config = {
            "integration_id": str(row.id),
            "method": row.method,
            "endpoint_host": row.endpoint.split("/")[2] if "//" in row.endpoint else row.endpoint,
        }
        if row.tool_id:
            tool = await self.session.get(Tool, row.tool_id)
            if tool is not None:
                await svc.update(
                    tool.id,
                    ToolUpdate(
                        display_name=row.name,
                        description=row.description or f"Calls {row.method} {row.endpoint}",
                        status="active" if row.status == "active" else "disabled",
                        input_schema=schema,
                        config=config,
                        timeout_seconds=row.timeout_seconds,
                        change_note="synced from integration",
                    ),
                )
                return await svc.get(tool.id)
        slug = f"api.{row.slug.replace('-', '_')}"
        tool = await svc.create(
            ToolCreate(
                slug=slug,
                display_name=row.name,
                description=row.description or f"Calls {row.method} {row.endpoint}",
                executor_type="http_api",
                input_schema=schema,
                config=config,
                timeout_seconds=row.timeout_seconds,
            )
        )
        row.tool_id = tool.id
        await self.session.flush()
        return tool

    # ------------------------------------------------------------------ test
    async def test(
        self,
        integration_id: uuid.UUID,
        variables: dict[str, Any],
        secrets: SecretStore,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> IntegrationTestOut:
        row = await self.get(integration_id)
        executor = HttpApiExecutor(
            session_factory,
            secrets,
            self.settings,
            transport=transport,
            context={"workspace_id": "test", "project_id": "test"},
        )
        revealed = await executor.reveal_secrets(row)
        rendered_preview: dict[str, Any]
        try:
            rendered_preview = executor.render_request(row, variables, revealed).masked
        except Exception as exc:  # missing secret etc.
            rendered_preview = {"error": str(exc)}
        result = await executor.send(row, variables, revealed)
        now = datetime.now(UTC)
        row.health_status = "ok" if result.ok else "error"
        row.health_message = (
            result.error_message or f"HTTP {result.output.get('status')} in {result.duration_ms} ms"
        )
        row.last_tested_at = now
        row.request_count += 1
        row.total_latency_ms += result.duration_ms
        if not result.ok:
            row.error_count += 1
        await self.session.flush()
        await self._audit(
            "integration.tested",
            row.id,
            after={"ok": result.ok, "status": result.output.get("status"), "latency_ms": result.duration_ms},
        )
        preview = result.output.get("json", result.output.get("text"))
        return IntegrationTestOut(
            ok=result.ok,
            request=rendered_preview,
            status=result.output.get("status"),
            latency_ms=result.duration_ms,
            response_size_bytes=result.output.get("size_bytes"),
            content_type=result.output.get("content_type"),
            response_preview=preview,
            file=result.output.get("file"),
            error_code=result.error_code,
            error_message=result.error_message,
            tested_at=now,
        )
