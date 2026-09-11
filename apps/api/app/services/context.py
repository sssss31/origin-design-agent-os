"""ContextManager (spec §7): selective, deterministic context for an agent run.

Sections are included only when relevant; large files are referenced (id, name, dimensions),
never pasted. Semantic retrieval is used when an EmbeddingProvider is available; otherwise
older messages are found with a keyword filter.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.chat import Message
from app.models.files import Artifact, Asset
from app.models.workspace import Project, Workspace
from app.ports.embeddings import EmbeddingProvider

_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{3,}")
STOP = {
    "please",
    "make",
    "this",
    "that",
    "with",
    "from",
    "into",
    "have",
    "want",
    "need",
    "should",
    "could",
    "would",
    "about",
}


@dataclass(slots=True)
class ContextPackage:
    summary: str
    sources: list[str] = field(default_factory=list)
    attachments: list[dict] = field(default_factory=list)


def _keywords(text: str, limit: int = 4) -> list[str]:
    words = [w.lower() for w in _WORD.findall(text) if w.lower() not in STOP and not w.startswith("/")]
    seen: list[str] = []
    for w in sorted(set(words), key=lambda w: (-len(w), w)):
        seen.append(w)
        if len(seen) >= limit:
            break
    return seen


async def build_context(
    session: AsyncSession,
    *,
    project: Project,
    workspace: Workspace,
    conversation_id: uuid.UUID,
    user_request: str,
    exclude_message_id: uuid.UUID | None,
    selected_asset_ids: list[uuid.UUID],
    selected_artifact_ids: list[uuid.UUID],
    embeddings: EmbeddingProvider,
    recent_limit: int = 10,
) -> ContextPackage:
    parts: list[str] = []
    sources: list[str] = []
    attachments: list[dict] = []

    parts.append(f"Project: {project.name}" + (f" — {project.description}" if project.description else ""))
    sources.append("project")
    if project.summary_text:
        parts.append("Project summary:\n" + project.summary_text.strip()[:4000])
        sources.append("project_summary")
    if workspace.brand_config:
        sources.append("brand_configuration")

    if selected_asset_ids:
        assets = (
            await session.scalars(
                select(Asset)
                .options(selectinload(Asset.versions))
                .where(Asset.id.in_(selected_asset_ids), Asset.project_id == project.id)
            )
        ).all()
        lines = []
        for a in assets:
            v = next((x for x in a.versions if x.id == a.current_version_id), None)
            dims = f", {v.width}x{v.height}px" if v and v.width else ""
            lines.append(f"- asset {a.id} '{a.name}' ({a.kind}{dims}, {v.mime_type if v else 'unknown'})")
            attachments.append(
                {"kind": "asset", "id": str(a.id), "name": a.name, "mime_type": v.mime_type if v else None}
            )
        if lines:
            parts.append("Selected assets (reference by id when calling tools):\n" + "\n".join(lines))
            sources.append("selected_assets")

    artifact_q = (
        select(Artifact).options(selectinload(Artifact.versions)).where(Artifact.project_id == project.id)
    )
    if selected_artifact_ids:
        artifact_q = artifact_q.where(Artifact.id.in_(selected_artifact_ids))
    else:
        artifact_q = (
            artifact_q.where(Artifact.status.in_(["approved", "final"]))
            .order_by(Artifact.updated_at.desc())
            .limit(5)
        )
    artifacts = (await session.scalars(artifact_q)).all()
    if artifacts:
        lines = []
        for art in artifacts:
            av = next((x for x in art.versions if x.id == art.current_version_id), None)
            dims = f", {av.width}x{av.height}px" if av and av.width else ""
            lines.append(
                f"- artifact {art.id} '{art.name}' av{av.version_number if av else '?'} [{art.status}] ({art.type}{dims})"
            )
            attachments.append(
                {
                    "kind": "artifact",
                    "id": str(art.id),
                    "name": art.name,
                    "status": art.status,
                    "mime_type": av.mime_type if av else None,
                }
            )
        parts.append(
            ("Selected artifacts" if selected_artifact_ids else "Latest approved artifacts")
            + ":\n"
            + "\n".join(lines)
        )
        sources.append("selected_artifacts" if selected_artifact_ids else "approved_artifacts")

    recent_q = select(Message).where(Message.conversation_id == conversation_id)
    if exclude_message_id is not None:
        recent_q = recent_q.where(Message.id != exclude_message_id)
    recent = list(
        (await session.scalars(recent_q.order_by(Message.created_at.desc()).limit(recent_limit))).all()
    )
    recent.reverse()
    if recent:
        parts.append(
            "Recent conversation:\n" + "\n".join(f"- {m.role}: {m.content.strip()[:300]}" for m in recent)
        )
        sources.append("recent_messages")

    keywords = _keywords(user_request)
    if keywords and not embeddings.available:
        recent_ids = {m.id for m in recent} | ({exclude_message_id} if exclude_message_id else set())
        older_q = (
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                or_(*[Message.content.ilike(f"%{k}%") for k in keywords]),
            )
            .order_by(Message.created_at.desc())
            .limit(5)
        )
        older = [m for m in (await session.scalars(older_q)).all() if m.id not in recent_ids]
        if older:
            parts.append(
                "Related earlier messages:\n"
                + "\n".join(f"- {m.role}: {m.content.strip()[:200]}" for m in older)
            )
            sources.append("keyword_relevant_messages")
    elif keywords and embeddings.available:
        sources.append("semantic_memory")  # Phase 4 opt-in when pgvector + embeddings are configured

    return ContextPackage(summary="\n\n".join(parts), sources=sources, attachments=attachments)
