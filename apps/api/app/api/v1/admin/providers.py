from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin import AdminAuth
from app.core.authz import DB, AuthContext
from app.core.deps import AdaptersDep
from app.core.errors import NotFound
from app.domain.provider_curl import ProviderCurl
from app.models.providers import AIProvider
from app.ports.secrets import key_preview
from app.schemas.admin import (
    ProviderConnectionOut,
    ProviderCreate,
    ProviderCurlIn,
    ProviderCurlPreview,
    ProviderImportOut,
    ProviderModelOut,
    ProviderModelsSet,
    ProviderOut,
    ProviderSecretIn,
    ProviderStatusOut,
    ProviderTestOut,
    ProviderUpdate,
)
from app.schemas.common import from_orm
from app.services.admin_serializers import provider_out
from app.services.providers import ProviderService

router = APIRouter(prefix="/providers")


@router.get("", response_model=list[ProviderOut])
async def list_providers(ctx: AdminAuth, session: DB) -> list[ProviderOut]:
    svc = ProviderService(session, ctx)
    return [provider_out(p, is_default=await svc.is_default(p.id)) for p in await svc.list()]


PROVIDER_TYPES = ("openai", "echo")


def _curl_preview(d: ProviderCurl) -> ProviderCurlPreview:
    return ProviderCurlPreview(
        provider_type=d.provider_type,
        base_url=d.base_url,
        endpoint_kind=d.endpoint_kind,
        has_key=d.api_key is not None,
        key_placeholder=d.key_placeholder,
        key_preview=key_preview(d.api_key) if d.api_key else None,
        model=d.model,
        instructions=d.instructions,
        sample_input=d.sample_input,
        model_settings=d.model_settings,
        has_output_schema=d.output_schema is not None,
        prompt_id=d.prompt_id,
        tools=d.tools,
        warnings=d.warnings,
        summary=d.summary(),
    )


@router.post("/parse-curl", response_model=ProviderCurlPreview)
async def parse_provider_curl_preview(body: ProviderCurlIn, ctx: AdminAuth) -> ProviderCurlPreview:
    """Dry run: what a pasted OpenAI cURL contains (key shown masked only)."""
    return _curl_preview(ProviderService.preview_curl(body.curl))


@router.post("/import-curl", response_model=ProviderImportOut, status_code=status.HTTP_201_CREATED)
async def import_provider_curl(
    body: ProviderCurlIn, ctx: AdminAuth, session: DB, adapters: AdaptersDep
) -> ProviderImportOut:
    """One paste: key stored encrypted, base URL, model allowlisted, default provider, connection tested."""
    svc = ProviderService(session, ctx)
    row, detected, created = await svc.import_curl(
        body.curl,
        adapters.secrets,
        name=body.name,
        environment=body.environment,
        set_default=body.set_default,
    )
    connection: ProviderConnectionOut | None = None
    if row.secret_ref_id is not None:
        result = await svc.test(row.id, adapters.secrets)
        connection = ProviderConnectionOut(
            success=result.ok,
            provider=row.type,
            status="connected" if result.ok else "failed",
            message=result.message,
            latency_ms=result.latency_ms,
            available_models=result.available_models,
            tested_at=result.tested_at,
        )
    row = await svc.get(row.id)
    return ProviderImportOut(
        provider=provider_out(row, is_default=await svc.is_default(row.id)),
        detected=_curl_preview(detected),
        connection=connection,
        created=created,
    )


def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


async def _by_type(session: AsyncSession, ctx: AuthContext, provider_type: str) -> AIProvider | None:
    if provider_type not in PROVIDER_TYPES:
        raise NotFound(f"Unknown provider type {provider_type}", code="provider_type_unknown")
    rows = [p for p in await ProviderService(session, ctx).list() if p.type == provider_type]
    enabled = [p for p in rows if p.enabled]
    candidates = enabled or rows
    return candidates[0] if candidates else None


async def _resolve(session: AsyncSession, ctx: AuthContext, ref: str) -> AIProvider:
    """`ref` is either a provider id or a provider type (spec: POST /providers/openai/test)."""
    pid = _as_uuid(ref)
    if pid is not None:
        return await ProviderService(session, ctx).get(pid)
    row = await _by_type(session, ctx, ref)
    if row is None:
        raise NotFound(f"No {ref} provider is configured", code="provider_not_configured")
    return row


@router.get("/{provider_ref}/status", response_model=ProviderStatusOut)
async def provider_status(provider_ref: str, ctx: AdminAuth, session: DB) -> ProviderStatusOut:
    """Spec §2 contract: `{provider, configured, key_preview}` and nothing more about the secret."""
    pid = _as_uuid(provider_ref)
    row = await ProviderService(session, ctx).get(pid) if pid else await _by_type(session, ctx, provider_ref)
    provider_type = row.type if row else provider_ref
    if row is None:
        return ProviderStatusOut(
            provider=provider_type,
            provider_id=None,
            name=None,
            configured=False,
            key_preview=None,
            status="not_configured",
            environment=None,
            enabled=False,
            last_tested_at=None,
        )
    configured = row.secret_ref_id is not None or row.type == "echo"
    status_label = (
        "connected" if row.health_status == "ok" else "failed" if row.health_status == "error" else "untested"
    )
    return ProviderStatusOut(
        provider=provider_type,
        provider_id=row.id,
        name=row.name,
        configured=configured,
        key_preview=row.key_preview,
        status=status_label if configured else "not_configured",
        environment=row.environment,
        enabled=row.enabled,
        last_tested_at=row.last_tested_at,
        models=[m.model for m in row.models if m.enabled],
        used_by=list(await ProviderService(session, ctx).agents_using(row.id)),
    )


@router.post("/{provider_ref}/connection-test", response_model=ProviderConnectionOut)
async def test_provider_connection(
    provider_ref: str, ctx: AdminAuth, session: DB, adapters: AdaptersDep
) -> ProviderConnectionOut:
    """Spec §3 contract (`{success, provider, status}`) by id or by type; sanitized on error."""
    row = await _resolve(session, ctx, provider_ref)
    result = await ProviderService(session, ctx).test(row.id, adapters.secrets)
    return ProviderConnectionOut(
        success=result.ok,
        provider=row.type,
        status="connected" if result.ok else "failed",
        message=result.message,
        latency_ms=result.latency_ms,
        available_models=result.available_models,
        tested_at=result.tested_at,
    )


@router.post("", response_model=ProviderOut, status_code=status.HTTP_201_CREATED)
async def create_provider(body: ProviderCreate, ctx: AdminAuth, session: DB) -> ProviderOut:
    return provider_out(await ProviderService(session, ctx).create(body))


@router.post("/{provider_id}/set-default", response_model=ProviderOut)
async def set_default_provider(provider_id: uuid.UUID, ctx: AdminAuth, session: DB) -> ProviderOut:
    """Agents without an explicit provider run on the default one — only the API key is needed."""
    svc = ProviderService(session, ctx)
    row = await svc.set_default(provider_id)
    return provider_out(row, is_default=True)


@router.post("/{provider_id}/adopt")
async def adopt_provider(
    provider_id: uuid.UUID, ctx: AdminAuth, session: DB, model: str | None = None
) -> dict[str, int]:
    """Switch every agent to this provider (draft + publish); sets it as default too."""
    svc = ProviderService(session, ctx)
    await svc.set_default(provider_id)
    return await svc.adopt(provider_id, model=model)


@router.delete("/{provider_id}/secret", response_model=ProviderOut)
async def delete_provider_secret(
    provider_id: uuid.UUID, ctx: AdminAuth, session: DB, adapters: AdaptersDep
) -> ProviderOut:
    return provider_out(await ProviderService(session, ctx).delete_secret(provider_id, adapters.secrets))


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(provider_id: uuid.UUID, ctx: AdminAuth, session: DB, adapters: AdaptersDep) -> None:
    await ProviderService(session, ctx).delete(provider_id, adapters.secrets)


@router.get("/{provider_id}/supported-models")
async def supported_models(
    provider_id: uuid.UUID, ctx: AdminAuth, session: DB, adapters: AdaptersDep
) -> list[dict]:
    """Vendor-known models with default capability flags (admin may allowlist any subset)."""
    row = await ProviderService(session, ctx).get(provider_id)
    adapter = adapters.providers.get(row.type)
    return adapter.get_supported_models() if adapter else []


@router.get("/{provider_id}", response_model=ProviderOut)
async def get_provider(provider_id: uuid.UUID, ctx: AdminAuth, session: DB) -> ProviderOut:
    return provider_out(await ProviderService(session, ctx).get(provider_id))


@router.patch("/{provider_id}", response_model=ProviderOut)
async def update_provider(
    provider_id: uuid.UUID, body: ProviderUpdate, ctx: AdminAuth, session: DB
) -> ProviderOut:
    return provider_out(await ProviderService(session, ctx).update(provider_id, body))


@router.post("/{provider_id}/secret", response_model=ProviderOut)
async def set_provider_secret(
    provider_id: uuid.UUID, body: ProviderSecretIn, ctx: AdminAuth, session: DB, adapters: AdaptersDep
) -> ProviderOut:
    """Write-only: stores the key through SecretStore; the response carries only a fingerprint."""
    return provider_out(
        await ProviderService(session, ctx).set_secret(provider_id, body.api_key, adapters.secrets)
    )


@router.post("/{provider_ref}/test", response_model=ProviderTestOut | ProviderConnectionOut)
async def test_provider(
    provider_ref: str, ctx: AdminAuth, session: DB, adapters: AdaptersDep
) -> ProviderTestOut | ProviderConnectionOut:
    """By id → detailed result; by type (`/providers/openai/test`) → spec §3 `{success, provider, status}`."""
    row = await _resolve(session, ctx, provider_ref)
    result = await ProviderService(session, ctx).test(row.id, adapters.secrets)
    if _as_uuid(provider_ref) is not None:
        return result
    return ProviderConnectionOut(
        success=result.ok,
        provider=row.type,
        status="connected" if result.ok else "failed",
        message=result.message,
        latency_ms=result.latency_ms,
        available_models=result.available_models,
        tested_at=result.tested_at,
    )


@router.get("/{provider_id}/models", response_model=list[ProviderModelOut])
async def list_models(provider_id: uuid.UUID, ctx: AdminAuth, session: DB) -> list[ProviderModelOut]:
    provider = await ProviderService(session, ctx).get(provider_id)
    return [from_orm(ProviderModelOut, m) for m in provider.models]


@router.put("/{provider_id}/models", response_model=ProviderOut)
async def set_models(
    provider_id: uuid.UUID, body: ProviderModelsSet, ctx: AdminAuth, session: DB
) -> ProviderOut:
    return provider_out(await ProviderService(session, ctx).set_models(provider_id, body))
