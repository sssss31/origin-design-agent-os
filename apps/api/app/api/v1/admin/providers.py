from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.v1.admin import AdminAuth
from app.core.authz import DB
from app.core.deps import AdaptersDep
from app.schemas.admin import (
    ProviderCreate,
    ProviderModelOut,
    ProviderModelsSet,
    ProviderOut,
    ProviderSecretIn,
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


@router.post("", response_model=ProviderOut, status_code=status.HTTP_201_CREATED)
async def create_provider(body: ProviderCreate, ctx: AdminAuth, session: DB) -> ProviderOut:
    return provider_out(await ProviderService(session, ctx).create(body))


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


@router.post("/{provider_id}/test", response_model=ProviderTestOut)
async def test_provider(
    provider_id: uuid.UUID, ctx: AdminAuth, session: DB, adapters: AdaptersDep
) -> ProviderTestOut:
    return await ProviderService(session, ctx).test(provider_id, adapters.secrets)


@router.get("/{provider_id}/models", response_model=list[ProviderModelOut])
async def list_models(provider_id: uuid.UUID, ctx: AdminAuth, session: DB) -> list[ProviderModelOut]:
    provider = await ProviderService(session, ctx).get(provider_id)
    return [from_orm(ProviderModelOut, m) for m in provider.models]


@router.put("/{provider_id}/models", response_model=ProviderOut)
async def set_models(
    provider_id: uuid.UUID, body: ProviderModelsSet, ctx: AdminAuth, session: DB
) -> ProviderOut:
    return provider_out(await ProviderService(session, ctx).set_models(provider_id, body))
