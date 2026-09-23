"""AI provider management: write-only secrets, connection tests, model allowlists (spec §6)."""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authz import AuthContext
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.logging import redact
from app.domain.slugs import slugify
from app.models.providers import AIProvider, ProviderModel
from app.ports.secrets import SecretStore, key_preview
from app.providers.base import AIProvider as ProviderAdapter
from app.schemas.admin import ProviderCreate, ProviderModelsSet, ProviderTestOut, ProviderUpdate
from app.services import audit

DEFAULT_BASE_URLS = {"openai": "https://api.openai.com/v1"}


def provider_adapters() -> dict[str, ProviderAdapter]:
    """Registered provider adapters by type (see app/adapters/registry.py)."""
    from app.adapters.registry import build_providers
    from app.core.config import get_settings

    return build_providers(get_settings())


@dataclass(slots=True)
class ProbeResult:
    ok: bool
    message: str
    models: list[str] = field(default_factory=list)


async def probe_provider(provider_type: str, base_url: str | None, api_key: str | None) -> ProbeResult:
    """Minimal authenticated request through the provider adapter. Never returns the key."""
    adapter = provider_adapters().get(provider_type)
    if adapter is None:
        return ProbeResult(ok=False, message=f"unsupported provider type {provider_type!r}")
    result = await adapter.test_connection({"base_url": base_url}, api_key)
    return ProbeResult(ok=result.ok, message=result.message, models=result.models)


def _snapshot(p: AIProvider) -> dict:
    return {
        "name": p.name,
        "type": p.type,
        "base_url": p.base_url,
        "enabled": p.enabled,
        "default_model": p.default_model,
        "rate_limit_policy": p.rate_limit_policy,
        "secret_fingerprint": p.secret_fingerprint,
        "key_preview": p.key_preview,
        "environment": p.environment,
    }


class ProviderService:
    def __init__(self, session: AsyncSession, ctx: AuthContext) -> None:
        self.session = session
        self.ctx = ctx
        self.org_id = ctx.require_organization()

    async def _audit(
        self, action: str, entity_id: uuid.UUID, before: dict | None = None, after: dict | None = None
    ) -> None:
        await audit.record(
            self.session,
            action=action,
            entity_type="ai_provider",
            entity_id=entity_id,
            organization_id=self.org_id,
            actor_user_id=self.ctx.user_id,
            before=before,
            after=after,
            request_id=self.ctx.request_id,
            ip_address=self.ctx.ip_address,
        )

    async def list(self) -> list[AIProvider]:
        rows = await self.session.scalars(
            select(AIProvider)
            .options(selectinload(AIProvider.models))
            .where(AIProvider.organization_id == self.org_id)
            .order_by(AIProvider.created_at)
        )
        return list(rows.all())

    async def get(self, provider_id: uuid.UUID) -> AIProvider:
        row = await self.session.scalar(
            select(AIProvider)
            .options(selectinload(AIProvider.models))
            .where(AIProvider.id == provider_id, AIProvider.organization_id == self.org_id)
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise NotFound("Provider not found", code="provider_not_found")
        return row

    async def create(self, data: ProviderCreate) -> AIProvider:
        slug = data.slug or slugify(data.name)
        if await self.session.scalar(
            select(AIProvider.id).where(AIProvider.organization_id == self.org_id, AIProvider.slug == slug)
        ):
            raise Conflict(f"Provider slug '{slug}' already exists", code="slug_taken")
        row = AIProvider(
            organization_id=self.org_id,
            name=data.name,
            slug=slug,
            type=data.type,
            base_url=data.base_url or DEFAULT_BASE_URLS.get(data.type),
            default_model=data.default_model,
            metadata_json=data.metadata_json,
            rate_limit_policy=data.rate_limit_policy,
            enabled=data.enabled,
            environment=data.environment,
            created_by=self.ctx.user_id,
            updated_by=self.ctx.user_id,
        )
        self.session.add(row)
        await self.session.flush()
        await self._audit("provider.created", row.id, after=_snapshot(row))
        return await self.get(row.id)

    async def update(self, provider_id: uuid.UUID, data: ProviderUpdate) -> AIProvider:
        row = await self.get(provider_id)
        before = _snapshot(row)
        for k, v in data.model_dump(exclude_unset=True).items():
            setattr(row, k, v)
        row.updated_by = self.ctx.user_id
        await self.session.flush()
        await self._audit("provider.updated", row.id, before=before, after=_snapshot(row))
        return await self.get(row.id)

    async def set_secret(self, provider_id: uuid.UUID, api_key: str, secrets: SecretStore) -> AIProvider:
        row = await self.get(provider_id)
        before = {"secret_fingerprint": row.secret_fingerprint}
        if row.secret_ref_id:
            handle = await secrets.rotate(str(row.secret_ref_id), api_key)
        else:
            handle = await secrets.store(f"provider:{row.slug}", api_key)
            row.secret_ref_id = uuid.UUID(handle.ref)
        row.secret_fingerprint = handle.fingerprint
        row.key_preview = key_preview(api_key)
        row.health_status = "unknown"
        row.health_message = None
        row.updated_by = self.ctx.user_id
        await self.session.flush()
        await self._audit(
            "provider.secret_set",
            row.id,
            before=before,
            after={
                "secret_fingerprint": handle.fingerprint,
                "secret_version": handle.version,
                "key_preview": row.key_preview,
            },
        )
        return await self.get(row.id)

    async def delete_secret(self, provider_id: uuid.UUID, secrets: SecretStore) -> AIProvider:
        row = await self.get(provider_id)
        before = {"key_preview": row.key_preview}
        if row.secret_ref_id:
            await secrets.delete(str(row.secret_ref_id))
        row.secret_ref_id = None
        row.secret_fingerprint = None
        row.key_preview = None
        row.health_status = "unknown"
        row.health_message = "credential removed"
        row.updated_by = self.ctx.user_id
        await self.session.flush()
        await self._audit("provider.secret_deleted", row.id, before=before, after={"key_preview": None})
        return await self.get(row.id)

    async def delete(self, provider_id: uuid.UUID, secrets: SecretStore) -> None:
        """Remove a provider. Refused while an active/draft agent version still points at it."""
        from app.models.agents import Agent, AgentVersion

        row = await self.get(provider_id)
        users = (
            (
                await self.session.execute(
                    select(Agent.name)
                    .join(AgentVersion, AgentVersion.agent_id == Agent.id)
                    .where(
                        AgentVersion.provider_id == row.id,
                        (Agent.active_version_id == AgentVersion.id) | (AgentVersion.published_at.is_(None)),
                    )
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        if users:
            raise Conflict(
                f"Provider is used by agents: {', '.join(sorted(users))}. Reassign them first.",
                code="provider_in_use",
                details=sorted(users),
            )
        if row.secret_ref_id:
            await secrets.delete(str(row.secret_ref_id))
        snapshot = _snapshot(row)
        await self.session.delete(row)
        await self.session.flush()
        await self._audit("provider.deleted", provider_id, before=snapshot)

    async def agents_using(self, provider_id: uuid.UUID) -> Sequence[str]:
        from app.models.agents import Agent, AgentVersion

        rows = await self.session.execute(
            select(Agent.name)
            .join(AgentVersion, AgentVersion.agent_id == Agent.id)
            .where(AgentVersion.provider_id == provider_id, Agent.active_version_id == AgentVersion.id)
            .distinct()
        )
        return sorted(rows.scalars().all())

    async def test(self, provider_id: uuid.UUID, secrets: SecretStore) -> ProviderTestOut:
        row = await self.get(provider_id)
        api_key: str | None = None
        lookup_error: str | None = None
        if row.secret_ref_id:
            try:
                api_key = await secrets.reveal(str(row.secret_ref_id))
            except LookupError as exc:
                lookup_error = str(exc)
        started = time.perf_counter()
        if lookup_error:
            result = ProbeResult(ok=False, message=f"stored secret cannot be read: {redact(lookup_error)}")
        else:
            result = await probe_provider(row.type, row.base_url, api_key)
        latency = int((time.perf_counter() - started) * 1000)
        now = datetime.now(UTC)
        row.health_status = "ok" if result.ok else "error"
        row.health_message = result.message
        row.last_tested_at = now
        await self.session.flush()
        await self._audit("provider.tested", row.id, after={"ok": result.ok, "message": result.message})
        return ProviderTestOut(
            ok=result.ok,
            message=result.message,
            latency_ms=latency,
            available_models=result.models[:200],
            tested_at=now,
        )

    async def set_models(self, provider_id: uuid.UUID, data: ProviderModelsSet) -> AIProvider:
        row = await self.get(provider_id)
        before = {"models": [m.model for m in row.models], "default_model": row.default_model}
        wanted = {m.model: m for m in data.models}
        if len(wanted) != len(data.models):
            raise ValidationFailed("duplicate model ids in allowlist", code="duplicate_models")
        existing = {m.model: m for m in row.models}
        for model_id, m in existing.items():
            if model_id not in wanted:
                await self.session.delete(m)
        for model_id, spec in wanted.items():
            target = existing.get(model_id)
            if target is None:
                self.session.add(
                    ProviderModel(
                        provider_id=row.id,
                        model=model_id,
                        display_name=spec.display_name,
                        capabilities=spec.capabilities,
                        enabled=spec.enabled,
                    )
                )
            else:
                target.display_name, target.capabilities, target.enabled = (
                    spec.display_name,
                    spec.capabilities,
                    spec.enabled,
                )
        if data.default_model is not None:
            if data.default_model and data.default_model not in wanted:
                raise ValidationFailed("default_model must be in the allowlist", code="default_not_allowed")
            row.default_model = data.default_model or None
        row.updated_by = self.ctx.user_id
        await self.session.flush()
        self.session.expire(row, ["models"])
        row = await self.get(row.id)
        await self._audit(
            "provider.models_set",
            row.id,
            before=before,
            after={"models": [m.model for m in row.models], "default_model": row.default_model},
        )
        return row

    async def allowed_models(self, provider: AIProvider) -> set[str]:
        return {m.model for m in provider.models if m.enabled}
