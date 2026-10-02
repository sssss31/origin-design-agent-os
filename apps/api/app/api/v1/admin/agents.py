from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, UploadFile, status

from app.api.v1.admin import AdminAuth
from app.core.authz import DB, Config
from app.core.deps import AdaptersDep
from app.schemas.admin import (
    AgentConnectionIn,
    AgentCreate,
    AgentCurlImportIn,
    AgentImportOut,
    AgentOut,
    AgentRuntimeIn,
    AgentSummaryOut,
    AgentTestOut,
    AgentTestRequest,
    AgentUpdate,
    AgentVersionInput,
    HandoffIn,
    NativeTestImageOut,
    NativeTestOut,
    ProviderConnectionOut,
    PublishRequest,
    SkillBindingIn,
    SkillOrderIn,
    ToolBindingIn,
)
from app.services.admin_serializers import agent_out, agent_summary_out, provider_out
from app.services.agents import AgentService, import_agent_from_curl, set_agent_connection, set_agent_runtime

router = APIRouter(prefix="/agents")


@router.get("", response_model=list[AgentSummaryOut])
async def list_agents(ctx: AdminAuth, session: DB) -> list[AgentSummaryOut]:
    return [agent_summary_out(a) for a in await AgentService(session, ctx).list()]


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def create_agent(body: AgentCreate, ctx: AdminAuth, session: DB) -> AgentOut:
    return await agent_out(session, await AgentService(session, ctx).create(body))


@router.post("/import-curl", response_model=AgentImportOut, status_code=status.HTTP_201_CREATED)
async def import_agent_curl(
    body: AgentCurlImportIn, ctx: AdminAuth, session: DB, adapters: AdaptersDep
) -> AgentImportOut:
    """Paste the agent's OpenAI cURL: provider key + model are configured and the agent is created."""
    from app.api.v1.admin.providers import _curl_preview
    from app.services.providers import ProviderService

    agent, provider, detected, published = await import_agent_from_curl(session, ctx, body, adapters)
    svc = ProviderService(session, ctx)
    connection = None
    if provider.secret_ref_id is not None:
        result = await svc.test(provider.id, adapters.secrets)
        from app.schemas.admin import ProviderConnectionOut

        connection = ProviderConnectionOut(
            success=result.ok,
            provider=provider.type,
            status="connected" if result.ok else "failed",
            message=result.message,
            latency_ms=result.latency_ms,
            available_models=result.available_models,
            tested_at=result.tested_at,
        )
    return AgentImportOut(
        agent=await agent_out(session, agent),
        provider=provider_out(await svc.get(provider.id), is_default=await svc.is_default(provider.id)),
        detected=_curl_preview(detected),
        published=published,
        connection=connection,
    )


@router.put("/{agent_id}/connection", response_model=AgentOut)
async def set_connection(
    agent_id: uuid.UUID, body: AgentConnectionIn, ctx: AdminAuth, session: DB, adapters: AdaptersDep
) -> AgentOut:
    """Workspace V0 §27: endpoint, API key (encrypted, write-only), connection config."""
    return await agent_out(session, await set_agent_connection(session, ctx, agent_id, body, adapters))


@router.post("/{agent_id}/test-connection", response_model=ProviderConnectionOut)
async def test_connection(
    agent_id: uuid.UUID, ctx: AdminAuth, session: DB, adapters: AdaptersDep, settings: Config
) -> ProviderConnectionOut:
    from datetime import UTC, datetime

    from app.services.agent_gateway import test_agent_connection

    svc = AgentService(session, ctx)
    agent = await svc.get(agent_id)
    if agent.connection_type == "origin":
        return ProviderConnectionOut(
            success=True,
            provider="origin",
            status="connected",
            message="Origin-built agent (uses a model provider).",
            latency_ms=0,
            tested_at=datetime.now(UTC),
        )
    result = await test_agent_connection(
        agent, adapters, settings, transport=getattr(adapters, "http_transport", None)
    )
    agent.connection_status = "ok" if result.ok else "error"
    agent.connection_message = result.message
    agent.connection_tested_at = datetime.now(UTC)
    await session.flush()
    await svc._audit("agent.connection_tested", agent.id, after={"ok": result.ok, "message": result.message})
    return ProviderConnectionOut(
        success=result.ok,
        provider=agent.connection_type,
        status="connected" if result.ok else "failed",
        message=result.message,
        latency_ms=result.latency_ms,
        available_models=result.models,
        tested_at=agent.connection_tested_at,
    )


@router.put("/{agent_id}/runtime", response_model=AgentOut)
async def set_runtime(
    agent_id: uuid.UUID, body: AgentRuntimeIn, ctx: AdminAuth, session: DB, adapters: AdaptersDep
) -> AgentOut:
    """Execution brief §8: execution_mode + native runtime configuration (key write-only)."""
    return await agent_out(session, await set_agent_runtime(session, ctx, agent_id, body, adapters))


@router.post("/{agent_id}/test-native", response_model=NativeTestOut)
async def test_native(
    agent_id: uuid.UUID,
    ctx: AdminAuth,
    session: DB,
    adapters: AdaptersDep,
    settings: Config,
    prompt: str = Form(..., min_length=1, max_length=20000),
    file: UploadFile | None = File(default=None),
) -> NativeTestOut:
    """Execution brief §25: run the native runtime once with an optional image; images come back inline.
    Nothing is written to a chat. Works in either execution mode so the runtime can be proven first."""
    import asyncio
    import base64
    from datetime import UTC, datetime

    from app.providers.existing.base import AgentCallError, AgentFile
    from app.services.agent_gateway import (
        NATIVE_RUNTIME,
        build_existing_providers,
        native_connection,
    )

    svc = AgentService(session, ctx)
    agent = await svc.get(agent_id)
    files: list[AgentFile] = []
    if file is not None:
        content = await file.read()
        if len(content) > settings.max_upload_mb * 1024 * 1024:
            return NativeTestOut(
                ok=False,
                text=None,
                latency_ms=0,
                error_code="file_too_large",
                error_message="The file is too large.",
            )
        files.append(
            AgentFile(
                name=file.filename or "upload",
                mime_type=file.content_type or "application/octet-stream",
                content=content,
            )
        )
    started = datetime.now(UTC)

    async def _noop(_: str) -> None:
        return None

    try:
        conn = await native_connection(agent, adapters)
        provider = build_existing_providers(settings, transport=getattr(adapters, "http_transport", None))[
            NATIVE_RUNTIME
        ]
        problems = provider.validate_config(conn)
        if problems:
            raise AgentCallError("agent_not_configured", f"{agent.name}: {'; '.join(problems)}")
        reply = await asyncio.wait_for(
            provider.send_message(
                conn,
                prompt,
                history=[],
                files=files,
                session_id=None,
                conversation_id=str(uuid.uuid4()),
                on_delta=_noop,
            ),
            timeout=float((agent.native_config or {}).get("timeout_seconds") or 180),
        )
    except AgentCallError as exc:
        return NativeTestOut(
            ok=False,
            text=None,
            latency_ms=int((datetime.now(UTC) - started).total_seconds() * 1000),
            error_code=exc.code,
            error_message=exc.message,
        )
    except TimeoutError:
        return NativeTestOut(
            ok=False,
            text=None,
            latency_ms=int((datetime.now(UTC) - started).total_seconds() * 1000),
            error_code="agent_timeout",
            error_message="The native runtime did not answer in time.",
        )
    await svc._audit("agent.native_tested", agent.id, after={"ok": True, "images": len(reply.files)})
    return NativeTestOut(
        ok=True,
        text=reply.text or None,
        images=[
            NativeTestImageOut(
                filename=f.filename,
                mime_type=f.mime_type,
                data_url=f"data:{f.mime_type};base64,{base64.b64encode(f.content).decode()}",
                revised_prompt=str(f.metadata.get("revised_prompt") or "") or None,
            )
            for f in reply.files
            if f.artifact_type == "image"
        ],
        latency_ms=int((datetime.now(UTC) - started).total_seconds() * 1000),
        response_id=reply.session_id,
    )


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(agent_id: uuid.UUID, ctx: AdminAuth, session: DB) -> AgentOut:
    return await agent_out(session, await AgentService(session, ctx).get(agent_id))


@router.patch("/{agent_id}", response_model=AgentOut)
async def update_agent(agent_id: uuid.UUID, body: AgentUpdate, ctx: AdminAuth, session: DB) -> AgentOut:
    return await agent_out(session, await AgentService(session, ctx).update(agent_id, body))


@router.post("/{agent_id}/versions", response_model=AgentOut)
async def save_agent_draft(
    agent_id: uuid.UUID, body: AgentVersionInput, ctx: AdminAuth, session: DB
) -> AgentOut:
    """Create or update the draft version. The active version is never mutated in place."""
    return await agent_out(session, await AgentService(session, ctx).save_draft(agent_id, body))


@router.post("/{agent_id}/publish", response_model=AgentOut)
async def publish_agent(agent_id: uuid.UUID, body: PublishRequest, ctx: AdminAuth, session: DB) -> AgentOut:
    """Publish the draft (validation gate) or roll back to a published `version_id`."""
    return await agent_out(session, await AgentService(session, ctx).publish(agent_id, body))


@router.post("/{agent_id}/test", response_model=AgentTestOut)
async def test_agent(
    agent_id: uuid.UUID, body: AgentTestRequest, ctx: AdminAuth, session: DB, adapters: AdaptersDep
) -> AgentTestOut:
    return await AgentService(session, ctx).test(agent_id, body, adapters)


@router.post("/{agent_id}/skills/{skill_id}", response_model=AgentOut)
async def attach_skill(
    agent_id: uuid.UUID, skill_id: uuid.UUID, ctx: AdminAuth, session: DB, body: SkillBindingIn | None = None
) -> AgentOut:
    return await agent_out(
        session, await AgentService(session, ctx).attach_skill(agent_id, skill_id, body or SkillBindingIn())
    )


@router.put("/{agent_id}/skills/order", response_model=AgentOut)
async def reorder_skills(agent_id: uuid.UUID, body: SkillOrderIn, ctx: AdminAuth, session: DB) -> AgentOut:
    return await agent_out(session, await AgentService(session, ctx).reorder_skills(agent_id, body.skill_ids))


@router.delete("/{agent_id}/skills/{skill_id}", response_model=AgentOut)
async def detach_skill(agent_id: uuid.UUID, skill_id: uuid.UUID, ctx: AdminAuth, session: DB) -> AgentOut:
    return await agent_out(session, await AgentService(session, ctx).detach_skill(agent_id, skill_id))


@router.post("/{agent_id}/tools/{tool_id}", response_model=AgentOut)
async def attach_tool(
    agent_id: uuid.UUID, tool_id: uuid.UUID, ctx: AdminAuth, session: DB, body: ToolBindingIn | None = None
) -> AgentOut:
    return await agent_out(
        session, await AgentService(session, ctx).attach_tool(agent_id, tool_id, body or ToolBindingIn())
    )


@router.delete("/{agent_id}/tools/{tool_id}", response_model=AgentOut)
async def detach_tool(agent_id: uuid.UUID, tool_id: uuid.UUID, ctx: AdminAuth, session: DB) -> AgentOut:
    return await agent_out(session, await AgentService(session, ctx).detach_tool(agent_id, tool_id))


@router.post("/{agent_id}/handoffs/{target_agent_id}", response_model=AgentOut)
async def add_handoff(
    agent_id: uuid.UUID,
    target_agent_id: uuid.UUID,
    ctx: AdminAuth,
    session: DB,
    body: HandoffIn | None = None,
) -> AgentOut:
    return await agent_out(
        session, await AgentService(session, ctx).add_handoff(agent_id, target_agent_id, body or HandoffIn())
    )


@router.delete("/{agent_id}/handoffs/{target_agent_id}", response_model=AgentOut)
async def remove_handoff(
    agent_id: uuid.UUID, target_agent_id: uuid.UUID, ctx: AdminAuth, session: DB
) -> AgentOut:
    return await agent_out(
        session, await AgentService(session, ctx).remove_handoff(agent_id, target_agent_id)
    )
