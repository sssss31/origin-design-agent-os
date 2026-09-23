from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin import AdminAuth
from app.core.authz import DB, AuthContext
from app.core.deps import AdaptersDep
from app.core.errors import NotFound
from app.models.providers import AIProvider
from app.schemas.admin import (
    ProviderConnectionOut,
    ProviderCreate,
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
    return [provider_out(p) for p in await ProviderService(session, ctx).list()]


PROVIDER_TYPES = ("openai", "echo")


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
