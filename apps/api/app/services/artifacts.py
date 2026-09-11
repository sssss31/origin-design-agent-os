"""Artifacts: versioned outputs with lineage (spec §8), approval/final states (spec §16 P7)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authz import AuthContext
from app.core.errors import NotFound, ValidationFailed
from app.domain.roles import Role
from app.models.agents import Agent, AgentVersion
from app.models.files import Artifact, ArtifactVersion
from app.ports.runner import ProducedFile
from app.ports.storage import ObjectStorage
from app.schemas.common import from_orm
from app.schemas.files import ArtifactOut, ArtifactVersionOut, LineageNode
from app.services import audit
from app.services.access import ProjectAccess, resolve_project
from app.services.uploads import safe_filename, sniff_image

# status transitions (spec §8 version flow / §19 QC failure keeps artifact non-final)
ARTIFACT_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"generated", "archived"},
    "generated": {"qc_failed", "approved", "archived", "final"},
    "qc_failed": {"generated", "archived"},
    "approved": {"final", "archived", "generated"},
    "final": {"archived"},
    "archived": set(),
}


class ArtifactService:
    def __init__(
        self,
        session: AsyncSession,
        ctx: AuthContext | None,
        storage: ObjectStorage,
        *,
        signed_url_ttl: int = 300,
    ) -> None:
        self.session = session
        self.ctx = ctx
        self.storage = storage
        self.signed_url_ttl = signed_url_ttl

    # ------------------------------------------------------------------ reads (authorized)
    async def _get(
        self, artifact_id: uuid.UUID, required: Role = Role.VIEWER
    ) -> tuple[Artifact, ProjectAccess]:
        assert self.ctx is not None
        art = await self.session.scalar(
            select(Artifact)
            .options(selectinload(Artifact.versions))
            .where(Artifact.id == artifact_id)
            .execution_options(populate_existing=True)
        )
        if art is None:
            raise NotFound("Artifact not found", code="artifact_not_found")
        access = await resolve_project(self.session, self.ctx, art.project_id)
        access.require(required)
        return art, access

    async def list_for_project(
        self, project_id: uuid.UUID, *, status: str | None = None, artifact_type: str | None = None
    ) -> list[Artifact]:
        assert self.ctx is not None
        await resolve_project(self.session, self.ctx, project_id)
        q = select(Artifact).options(selectinload(Artifact.versions)).where(Artifact.project_id == project_id)
        if status:
            q = q.where(Artifact.status == status)
        if artifact_type:
            q = q.where(Artifact.type == artifact_type)
        return list((await self.session.scalars(q.order_by(Artifact.created_at.desc()))).all())

    async def get(self, artifact_id: uuid.UUID) -> Artifact:
        art, _ = await self._get(artifact_id)
        return art

    async def set_status(self, artifact_id: uuid.UUID, status: str) -> Artifact:
        art, access = await self._get(artifact_id, Role.MEMBER)
        if status not in ARTIFACT_TRANSITIONS.get(art.status, set()):
            raise ValidationFailed(
                f"artifact cannot go from {art.status} to {status}", code="illegal_artifact_transition"
            )
        before = art.status
        art.status = status
        if status == "approved":
            art.approved_by = self.ctx.user_id if self.ctx else None
            art.approved_at = datetime.now(UTC)
        await self.session.flush()
        await audit.record(
            self.session,
            action=f"artifact.{status}",
            entity_type="artifact",
            entity_id=art.id,
            organization_id=access.workspace.organization_id,
            actor_user_id=self.ctx.user_id if self.ctx else None,
            before={"status": before},
            after={"status": status},
            request_id=self.ctx.request_id if self.ctx else None,
        )
        art, _ = await self._get(art.id)
        return art

    async def approve(self, artifact_id: uuid.UUID) -> Artifact:
        return await self.set_status(artifact_id, "approved")

    async def download_url(
        self, artifact_id: uuid.UUID, version_id: uuid.UUID | None = None
    ) -> tuple[str, ArtifactVersion]:
        art, _ = await self._get(artifact_id)
        version = next((v for v in art.versions if v.id == (version_id or art.current_version_id)), None)
        if version is None:
            raise NotFound("Artifact version not found", code="artifact_version_not_found")
        return await self.storage.presign_download(
            version.storage_key, expires_in=self.signed_url_ttl, filename=version.filename
        ), version

    async def lineage(self, artifact_id: uuid.UUID) -> LineageNode:
        art, _ = await self._get(artifact_id)
        # walk up to the root, then build the tree downwards within the project
        root = art
        seen = {root.id}
        while root.parent_artifact_id and root.parent_artifact_id not in seen:
            parent = await self.session.scalar(
                select(Artifact)
                .options(selectinload(Artifact.versions))
                .where(Artifact.id == root.parent_artifact_id)
            )
            if parent is None:
                break
            seen.add(parent.id)
            root = parent
        all_rows = list(
            (
                await self.session.scalars(
                    select(Artifact)
                    .options(selectinload(Artifact.versions))
                    .where(Artifact.project_id == art.project_id)
                )
            ).all()
        )
        by_parent: dict[uuid.UUID | None, list[Artifact]] = {}
        for a in all_rows:
            by_parent.setdefault(a.parent_artifact_id, []).append(a)
        agents = await _producer_slugs(self.session, all_rows)

        def build(node: Artifact, depth: int = 0) -> LineageNode:
            children = sorted(by_parent.get(node.id, []), key=lambda a: a.created_at) if depth < 12 else []
            return LineageNode(
                artifact=artifact_out(node, agents), children=[build(c, depth + 1) for c in children]
            )

        return build(root)

    # ---------------------------------------------------- writes from the run executor (pre-authorized)
    async def persist_produced(
        self,
        file: ProducedFile,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        run_id: uuid.UUID | None,
        node_run_id: uuid.UUID | None,
        agent_version_id: uuid.UUID | None,
        organization_id: uuid.UUID,
        created_by: uuid.UUID | None,
        parent_artifact_id: uuid.UUID | None = None,
        status: str = "generated",
        name: str | None = None,
    ) -> tuple[Artifact, ArtifactVersion]:
        """Store a produced file as a new artifact, or as a new version of an existing one."""
        filename = safe_filename(file.filename)
        prefix = f"org/{organization_id}/projects/{project_id}/artifacts/{run_id or 'manual'}"
        key = f"{prefix}/{uuid.uuid4().hex}-{filename}"
        stored = await self.storage.put(key, file.content, content_type=file.mime_type)
        width, height, meta = sniff_image(file.content, file.mime_type)
        meta.update(file.metadata)
        artifact_name = name or file.metadata.get("artifact_name") or filename
        existing = None
        if file.metadata.get("new_version_of"):
            existing = await self.session.scalar(
                select(Artifact)
                .options(selectinload(Artifact.versions))
                .where(Artifact.id == uuid.UUID(str(file.metadata["new_version_of"])))
            )
        if existing is None:
            existing = Artifact(
                workspace_id=workspace_id,
                project_id=project_id,
                conversation_id=conversation_id,
                name=artifact_name,
                type=file.artifact_type,
                status=status,
                parent_artifact_id=parent_artifact_id,
                created_by=created_by,
            )
            self.session.add(existing)
            await self.session.flush()
            number = 1
        else:
            number = max((v.version_number for v in existing.versions), default=0) + 1
            existing.status = status
        version = ArtifactVersion(
            artifact_id=existing.id,
            version_number=number,
            run_id=run_id,
            node_run_id=node_run_id,
            produced_by_agent_version_id=agent_version_id,
            storage_key=stored.key,
            filename=filename,
            mime_type=file.mime_type,
            size_bytes=stored.size,
            checksum_sha256=hashlib.sha256(file.content).hexdigest(),
            width=width,
            height=height,
            dpi=meta.get("dpi"),
            metadata_json=meta,
            created_by=created_by,
        )
        self.session.add(version)
        await self.session.flush()
        existing.current_version_id = version.id
        await self.session.flush()
        return existing, version

    async def read_bytes(self, version: ArtifactVersion) -> bytes:
        return await self.storage.get(version.storage_key)


async def _producer_slugs(session: AsyncSession, artifacts: list[Artifact]) -> dict[uuid.UUID, str]:
    version_ids = {
        v.produced_by_agent_version_id
        for a in artifacts
        for v in a.versions
        if v.produced_by_agent_version_id
    }
    if not version_ids:
        return {}
    rows = (
        await session.execute(
            select(AgentVersion.id, Agent.slug)
            .join(Agent, Agent.id == AgentVersion.agent_id)
            .where(AgentVersion.id.in_(version_ids))
        )
    ).all()
    return {vid: slug for vid, slug in rows}


def artifact_out(a: Artifact, producers: dict[uuid.UUID, str] | None = None) -> ArtifactOut:
    versions = sorted(a.versions, key=lambda v: v.version_number)
    current = next((v for v in versions if v.id == a.current_version_id), None)
    slug = None
    if current and producers and current.produced_by_agent_version_id:
        slug = producers.get(current.produced_by_agent_version_id)
    return from_orm(
        ArtifactOut,
        a,
        current_version=from_orm(ArtifactVersionOut, current) if current else None,
        versions=[from_orm(ArtifactVersionOut, v) for v in versions],
        producer_agent_slug=slug,
    )


async def artifacts_out(session: AsyncSession, artifacts: list[Artifact]) -> list[ArtifactOut]:
    producers = await _producer_slugs(session, artifacts)
    return [artifact_out(a, producers) for a in artifacts]
