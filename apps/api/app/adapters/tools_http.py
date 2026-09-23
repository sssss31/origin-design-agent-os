"""ToolExecutor for `http_api` tools backed by a CustomIntegration row.

Pipeline: load integration + secret refs → reveal secrets server-side → render endpoint,
query, headers and body templates → SSRF-validate the final URL → send with httpx (no
redirects, bounded timeout, bounded response size) → return a structured result. Binary
responses (images, SVG, PDF) become ProducedFiles so the runtime stores them as artifacts.
Credentials never appear in the result, events or logs.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.logging import get_logger, redact
from app.core.ssrf import OutboundBlocked, validate_outbound_url
from app.domain.templates import MissingSecret, mask_secrets, render, render_mapping
from app.models.integrations import CustomIntegration
from app.ports.runner import ProducedFile
from app.ports.secrets import SecretStore
from app.ports.tools import ExecutorType, ToolCall, ToolResult

log = get_logger("tools.http")

FILE_TYPES = {
    "image/png": ("png", "image"),
    "image/jpeg": ("jpg", "image"),
    "image/webp": ("webp", "image"),
    "image/svg+xml": ("svg", "svg"),
    "application/pdf": ("pdf", "pdf"),
}
PREVIEW_CHARS = 4000


@dataclass(slots=True)
class RenderedRequest:
    method: str
    url: str
    headers: dict[str, str]
    params: dict[str, str]
    body: bytes | None
    content_type: str
    masked: dict[str, Any] = field(default_factory=dict)


class HttpApiExecutor:
    executor_type = ExecutorType.HTTP_API

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        secrets: SecretStore,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.secrets = secrets
        self.settings = settings
        self.transport = transport
        self.context = context or {}

    # ------------------------------------------------------------------ rendering
    async def load(self, session: AsyncSession, integration_id: uuid.UUID) -> CustomIntegration | None:
        return await session.scalar(
            select(CustomIntegration)
            .options(selectinload(CustomIntegration.secrets))
            .where(CustomIntegration.id == integration_id)
        )

    async def reveal_secrets(self, integration: CustomIntegration) -> dict[str, str]:
        out: dict[str, str] = {}
        for s in integration.secrets:
            out[s.name] = await self.secrets.reveal(str(s.secret_ref_id))
        return out

    def render_request(
        self, integration: CustomIntegration, variables: dict[str, Any], secrets: dict[str, str]
    ) -> RenderedRequest:
        merged = {**self.context, **variables}
        url = render(integration.endpoint, variables=merged, secrets=secrets)
        headers = render_mapping(integration.headers_template, variables=merged, secrets=secrets)
        params = render_mapping(integration.query_template, variables=merged, secrets=secrets)
        body: bytes | None = None
        ctype = integration.content_type
        if integration.body_template and integration.method.upper() not in ("GET", "HEAD"):
            text = render(
                integration.body_template,
                variables=merged,
                secrets=secrets,
                json_mode=ctype.startswith("application/json"),
            )
            body = text.encode()
            headers.setdefault("Content-Type", ctype)
        masked_headers = {k: mask_secrets(v, secrets) for k, v in headers.items()}
        masked = {
            "method": integration.method.upper(),
            "url": mask_secrets(url, secrets),
            "query": {k: mask_secrets(v, secrets) for k, v in params.items()},
            "headers": masked_headers,
            "body": mask_secrets(body.decode(errors="replace"), secrets)[:PREVIEW_CHARS] if body else None,
        }
        return RenderedRequest(integration.method.upper(), url, headers, params, body, ctype, masked)

    # ------------------------------------------------------------------ execution
    async def execute(self, call: ToolCall) -> ToolResult:
        integration_id = call.tool.config.get("integration_id")
        if not integration_id:
            return ToolResult(
                ok=False, error_code="integration_missing", error_message="tool has no integration"
            )
        async with self.session_factory() as session:
            integration = await self.load(session, uuid.UUID(str(integration_id)))
            if integration is None:
                return ToolResult(
                    ok=False, error_code="integration_missing", error_message="integration not found"
                )
            if integration.status != "active":
                return ToolResult(
                    ok=False, error_code="integration_disabled", error_message="integration is disabled"
                )
            try:
                secrets = await self.reveal_secrets(integration)
            except LookupError:
                return ToolResult(
                    ok=False, error_code="secret_unavailable", error_message="a secret could not be read"
                )
            result = await self.send(integration, call.arguments, secrets)
            integration.request_count += 1
            integration.total_latency_ms += result.duration_ms
            if not result.ok:
                integration.error_count += 1
            await session.commit()
            return result

    async def send(
        self, integration: CustomIntegration, variables: dict[str, Any], secrets: dict[str, str]
    ) -> ToolResult:
        started = time.perf_counter()
        try:
            req = self.render_request(integration, variables, secrets)
        except MissingSecret as exc:
            return ToolResult(
                ok=False,
                error_code="secret_missing",
                error_message=f"secret {exc.args[0]!r} is not configured",
            )
        try:
            validate_outbound_url(req.url, self.settings)
        except OutboundBlocked as exc:
            return ToolResult(ok=False, error_code="outbound_blocked", error_message=str(exc))
        timeout = min(integration.timeout_seconds, self.settings.outbound_default_timeout_seconds * 10)
        limit = min(integration.max_response_bytes, self.settings.outbound_max_response_bytes)
        try:
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=False, transport=self.transport, max_redirects=0
            ) as client:
                async with client.stream(
                    req.method, req.url, headers=req.headers, params=req.params or None, content=req.body
                ) as res:
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in res.aiter_bytes():
                        size += len(chunk)
                        if size > limit:
                            return ToolResult(
                                ok=False,
                                error_code="response_too_large",
                                error_message=f"response exceeded {limit} bytes",
                                duration_ms=int((time.perf_counter() - started) * 1000),
                            )
                        chunks.append(chunk)
                    raw = b"".join(chunks)
                    status = res.status_code
                    ctype = (res.headers.get("content-type") or "").split(";")[0].strip().lower()
        except httpx.TimeoutException:
            return ToolResult(
                ok=False,
                error_code="timeout",
                error_message=f"no response within {timeout}s",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except httpx.HTTPError as exc:
            log.warning("http_tool_failed", integration=integration.slug, detail=redact(str(exc))[:200])
            return ToolResult(
                ok=False,
                error_code="request_failed",
                error_message="the endpoint could not be reached",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        duration = int((time.perf_counter() - started) * 1000)
        output: dict[str, Any] = {
            "status": status,
            "content_type": ctype,
            "size_bytes": len(raw),
            "latency_ms": duration,
        }
        files: list[Any] = []
        if ctype in FILE_TYPES:
            ext, artifact_type = FILE_TYPES[ctype]
            files.append(
                ProducedFile(
                    filename=f"{integration.slug}-{uuid.uuid4().hex[:8]}.{ext}",
                    content=raw,
                    mime_type=ctype,
                    artifact_type=artifact_type,
                    metadata={"integration": integration.slug, "status": status},
                )
            )
            output["file"] = files[0].filename
        else:
            text = raw.decode(errors="replace")
            if ctype.endswith("json") or text.lstrip().startswith(("{", "[")):
                try:
                    output["json"] = json.loads(text)
                except json.JSONDecodeError:
                    output["text"] = text[:PREVIEW_CHARS]
            else:
                output["text"] = text[:PREVIEW_CHARS]
        output = redact(output)
        ok = 200 <= status < 300
        return ToolResult(
            ok=ok,
            output=output,
            error_code=None if ok else f"http_{status}",
            error_message=None if ok else f"endpoint returned HTTP {status}",
            duration_ms=duration,
            files=files,
        )
