"""Dashboard endpoints: cross-project recents, library, agent graph and quick-start runs.

Everything is scoped to workspaces the caller can access (org admins see all workspaces).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authz import DB, Auth, AuthContext, Config
from app.core.deps import AdaptersDep
from app.domain.roles import Role
from app.models.agents import Agent, AgentToolBinding, AgentVersion
from app.models.chat import Conversation, Message
from app.models.files import Artifact, Asset
from app.models.tools import Tool
from app.models.workspace import Project, Workspace, WorkspaceMember
from app.schemas.chat import ConversationCreate, ConversationOut
from app.schemas.common import from_orm
from app.schemas.files import ArtifactOut, AssetOut, AssetVersionOut
from app.schemas.runs import RunCreate, RunCreated
from app.schemas.workspace import ProjectCreate, WorkspaceCreate
from app.services.artifacts import artifacts_out
from app.services.conversations import ConversationService
from app.services.projects import ProjectService
from app.services.runs import RunService
from app.services.workspaces import WorkspaceService

router = APIRouter(tags=["dashboard"])


async def accessible_project_ids(
    session: AsyncSession, ctx: AuthContext
) -> dict[uuid.UUID, tuple[Project, Workspace]]:
    org_ids = [ctx.organization_id] if ctx.organization_id else list(ctx.memberships)
    if not org_ids:
        return {}
    rows = (
        await session.execute(
            select(Project, Workspace, WorkspaceMember.role)
            .join(Workspace, Workspace.id == Project.workspace_id)
            .outerjoin(
                WorkspaceMember,
                (WorkspaceMember.workspace_id == Workspace.id) & (WorkspaceMember.user_id == ctx.user_id),
            )
            .where(Workspace.organization_id.in_(org_ids), Project.status == "active")
        )
    ).all()
    out: dict[uuid.UUID, tuple[Project, Workspace]] = {}
    for project, workspace, member_role in rows:
        if ctx.is_org_admin(workspace.organization_id) or member_role is not None:
            out[project.id] = (project, workspace)
    return out


class RecentConversation(ConversationOut):
    project_name: str
    workspace_name: str
    workspace_id: uuid.UUID
    last_message_preview: str | None = None


@router.get("/conversations/recent", response_model=list[RecentConversation])
async def recent_conversations(
    ctx: Auth,
    session: DB,
    limit: int = Query(default=30, ge=1, le=200),
    search: str | None = Query(default=None, max_length=200),
    include_archived: bool = False,
) -> list[RecentConversation]:
    projects = await accessible_project_ids(session, ctx)
    if not projects:
        return []
    q = select(Conversation).where(Conversation.project_id.in_(projects.keys()))
    if not include_archived:
        q = q.where(Conversation.status == "active")
    if search:
        sub = select(Message.conversation_id).where(Message.content.ilike(f"%{search}%"))
        q = q.where(or_(Conversation.title.ilike(f"%{search}%"), Conversation.id.in_(sub)))
    rows = (
        await session.scalars(
            q.order_by(
                Conversation.last_message_at.desc().nulls_last(), Conversation.created_at.desc()
            ).limit(limit)
        )
    ).all()
    previews: dict[uuid.UUID, str] = {}
    if rows:
        last = (
            await session.execute(
                select(Message.conversation_id, Message.content)
                .where(Message.conversation_id.in_([c.id for c in rows]))
                .order_by(Message.conversation_id, Message.created_at.desc())
                .distinct(Message.conversation_id)
            )
        ).all()
        previews = {cid: content[:120] for cid, content in last}
    out = []
    for c in rows:
        project, workspace = projects[c.project_id]
        out.append(
            from_orm(
                RecentConversation,
                c,
                project_name=project.name,
                workspace_name=workspace.name,
                workspace_id=workspace.id,
                last_message_preview=previews.get(c.id),
            )
        )
    return out


class LibraryOut(BaseModel):
    artifacts: list[ArtifactOut]
    assets: list[AssetOut]
    projects: list[dict[str, Any]]


@router.get("/library", response_model=LibraryOut)
async def library(
    ctx: Auth,
    session: DB,
    limit: int = Query(default=60, ge=1, le=300),
    project_id: uuid.UUID | None = None,
    artifact_status: str | None = None,
) -> LibraryOut:
    projects = await accessible_project_ids(session, ctx)
    ids = [project_id] if project_id and project_id in projects else list(projects.keys())
    if not ids:
        return LibraryOut(artifacts=[], assets=[], projects=[])
    aq = select(Artifact).options(selectinload(Artifact.versions)).where(Artifact.project_id.in_(ids))
    if artifact_status:
        aq = aq.where(Artifact.status == artifact_status)
    artifacts = (await session.scalars(aq.order_by(Artifact.updated_at.desc()).limit(limit))).all()
    assets = (
        await session.scalars(
            select(Asset)
            .options(selectinload(Asset.versions))
            .where(Asset.project_id.in_(ids), Asset.status == "ready")
            .order_by(Asset.created_at.desc())
            .limit(limit)
        )
    ).all()

    def asset_out(a: Asset) -> AssetOut:
        current = next((v for v in a.versions if v.id == a.current_version_id), None)
        return from_orm(
            AssetOut, a, current_version=from_orm(AssetVersionOut, current) if current else None, versions=[]
        )

    return LibraryOut(
        artifacts=await artifacts_out(session, list(artifacts)),
        assets=[asset_out(a) for a in assets],
        projects=[
            {"id": str(pid), "name": p.name, "workspace_id": str(w.id), "workspace_name": w.name}
            for pid, (p, w) in projects.items()
        ],
    )


class GraphNode(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    command: str
    description: str
    is_manager: bool
    status: str
    version: int | None
    model: str | None
    tools: list[str]
    skills_count: int


class GraphEdge(BaseModel):
    source: uuid.UUID
    target: uuid.UUID
    routing_hint: str
    is_failure_route: bool


class AgentGraph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


@router.get("/agents/graph", response_model=AgentGraph)
async def agent_graph(ctx: Auth, session: DB) -> AgentGraph:
    org_id = ctx.require_organization()
    agents = (
        await session.scalars(
            select(Agent)
            .options(
                selectinload(Agent.versions).selectinload(AgentVersion.handoffs),
                selectinload(Agent.versions).selectinload(AgentVersion.skill_bindings),
                selectinload(Agent.versions).selectinload(AgentVersion.tool_bindings),
            )
            .where(Agent.organization_id == org_id, Agent.status != "disabled")
        )
    ).all()
    tool_ids: set[uuid.UUID] = set()
    active_versions: dict[uuid.UUID, AgentVersion] = {}
    for a in agents:
        v = next((x for x in a.versions if x.id == a.active_version_id), None) or next(
            (x for x in a.versions if x.published_at is None), None
        )
        if v is not None:
            active_versions[a.id] = v
            tool_ids.update(b.tool_id for b in v.tool_bindings if b.enabled)
    tools = (
        {t.id: t.slug for t in (await session.scalars(select(Tool).where(Tool.id.in_(tool_ids)))).all()}
        if tool_ids
        else {}
    )
    nodes = []
    edges = []
    ids = {a.id for a in agents}
    for a in agents:
        v = active_versions.get(a.id)
        nodes.append(
            GraphNode(
                id=a.id,
                name=a.name,
                slug=a.slug,
                command=a.command,
                description=a.description,
                is_manager=a.is_manager,
                status=a.status,
                version=v.version if v else None,
                model=v.model if v else None,
                tools=sorted(
                    tools[b.tool_id]
                    for b in (v.tool_bindings if v else [])
                    if b.enabled and b.tool_id in tools
                ),
                skills_count=len([b for b in (v.skill_bindings if v else []) if b.enabled]),
            )
        )
        for h in v.handoffs if v else []:
            if h.target_agent_id in ids:
                edges.append(
                    GraphEdge(
                        source=a.id,
                        target=h.target_agent_id,
                        routing_hint=h.routing_hint,
                        is_failure_route=h.is_failure_route,
                    )
                )
    _ = AgentToolBinding
    return AgentGraph(nodes=nodes, edges=edges)


class QuickStartRequest(BaseModel):
    content: str = Field(min_length=1, max_length=50000)
    project_id: uuid.UUID | None = None
    selected_asset_ids: list[uuid.UUID] = Field(default_factory=list)
    title: str | None = Field(default=None, max_length=200)


class QuickStartOut(BaseModel):
    conversation_id: uuid.UUID
    project_id: uuid.UUID
    run: RunCreated


SCRATCH_WORKSPACE = "Playground"
SCRATCH_PROJECT = "Scratchpad"


async def ensure_scratch_project(session: AsyncSession, ctx: AuthContext) -> Project:
    """A personal-by-default place to start from the home composer without picking a project first."""
    projects = await accessible_project_ids(session, ctx)
    for project, workspace in projects.values():
        if workspace.slug == "playground" and project.slug == "scratchpad":
            return project
    ws_service = WorkspaceService(session, ctx)
    scratch = next((w for w, _ in await ws_service.list_visible() if w.slug == "playground"), None)
    if scratch is None:
        scratch, _ = await ws_service.create(
            WorkspaceCreate(
                name=SCRATCH_WORKSPACE, description="Quick experiments started from the home screen"
            )
        )
    project, _ = await ProjectService(session, ctx).create(scratch.id, ProjectCreate(name=SCRATCH_PROJECT))
    return project


@router.post("/quickstart", response_model=QuickStartOut, status_code=status.HTTP_202_ACCEPTED)
async def quickstart(
    body: QuickStartRequest, ctx: Auth, session: DB, adapters: AdaptersDep, settings: Config
) -> QuickStartOut:
    """Home-screen composer: pick (or create) a project, open a conversation and start the run in one call."""
    if body.project_id is not None:
        projects = await accessible_project_ids(session, ctx)
        if body.project_id not in projects:
            from app.core.errors import NotFound

            raise NotFound("Project not found", code="project_not_found")
        project = projects[body.project_id][0]
    else:
        project = await ensure_scratch_project(session, ctx)
    conv = await ConversationService(session, ctx).create(project.id, ConversationCreate(title=body.title))
    svc = RunService(session, ctx, adapters, settings)
    run = await svc.create(
        conv.id, RunCreate(content=body.content, selected_asset_ids=body.selected_asset_ids)
    )
    return QuickStartOut(
        conversation_id=conv.id,
        project_id=project.id,
        run=RunCreated(
            run_id=run.id,
            status=run.status,
            event_stream_url=svc.stream_url(run.id),
            message_id=run.message_id,
        ),
    )


class ProfileOut(BaseModel):
    display_name: str
    email: str
    role: Role | None
    organization_name: str | None
    counts: dict[str, int]
    joined_at: datetime


@router.get("/me/profile", response_model=ProfileOut)
async def profile(ctx: Auth, session: DB) -> ProfileOut:
    projects = await accessible_project_ids(session, ctx)
    ids = list(projects.keys())
    from sqlalchemy import func

    convs = (
        await session.scalar(select(func.count(Conversation.id)).where(Conversation.project_id.in_(ids)))
        if ids
        else 0
    )
    arts = (
        await session.scalar(select(func.count(Artifact.id)).where(Artifact.project_id.in_(ids)))
        if ids
        else 0
    )
    org = ctx.organizations.get(ctx.organization_id) if ctx.organization_id else None
    return ProfileOut(
        display_name=ctx.user.display_name,
        email=ctx.user.email,
        role=ctx.organization_role,
        organization_name=org.name if org else None,
        counts={"projects": len(ids), "conversations": int(convs or 0), "artifacts": int(arts or 0)},
        joined_at=ctx.user.created_at,
    )


class RecentRun(BaseModel):
    id: uuid.UUID
    status: str
    command: str | None
    user_input: str
    conversation_id: uuid.UUID
    conversation_title: str
    project_id: uuid.UUID
    project_name: str
    created_at: datetime
    finished_at: datetime | None
    node_statuses: dict[str, str]
    agent_slugs: list[str]


@router.get("/runs/recent", response_model=list[RecentRun])
async def recent_runs(
    ctx: Auth, session: DB, limit: int = Query(default=20, ge=1, le=100)
) -> list[RecentRun]:
    """Latest runs across accessible projects, with per-node status for the Nodes canvas."""
    from app.models.workflows import NodeRun, WorkflowRun

    projects = await accessible_project_ids(session, ctx)
    if not projects:
        return []
    runs = (
        await session.scalars(
            select(WorkflowRun)
            .options(selectinload(WorkflowRun.nodes))
            .where(WorkflowRun.project_id.in_(projects.keys()))
            .order_by(WorkflowRun.created_at.desc())
            .limit(limit)
        )
    ).all()
    conv_ids = {r.conversation_id for r in runs}
    titles = (
        {
            c.id: c.title
            for c in (await session.scalars(select(Conversation).where(Conversation.id.in_(conv_ids)))).all()
        }
        if conv_ids
        else {}
    )
    agent_ids = {n.agent_id for r in runs for n in r.nodes if n.agent_id}
    slugs = (
        {a.id: a.slug for a in (await session.scalars(select(Agent).where(Agent.id.in_(agent_ids)))).all()}
        if agent_ids
        else {}
    )
    out = []
    for r in runs:
        nodes: list[NodeRun] = sorted(r.nodes, key=lambda n: n.index)
        out.append(
            RecentRun(
                id=r.id,
                status=r.status,
                command=r.command,
                user_input=r.user_input[:200],
                conversation_id=r.conversation_id,
                conversation_title=titles.get(r.conversation_id, "Chat"),
                project_id=r.project_id,
                project_name=projects[r.project_id][0].name,
                created_at=r.created_at,
                finished_at=r.finished_at,
                node_statuses={
                    slugs[n.agent_id]: n.status for n in nodes if n.agent_id and n.agent_id in slugs
                },
                agent_slugs=[slugs[n.agent_id] for n in nodes if n.agent_id and n.agent_id in slugs],
            )
        )
    return out
