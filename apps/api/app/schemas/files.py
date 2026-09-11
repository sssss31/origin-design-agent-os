from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class AssetVersionOut(ORMModel):
    id: uuid.UUID
    version: int
    filename: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str
    width: int | None
    height: int | None
    metadata_json: dict[str, Any]
    created_at: datetime


class AssetOut(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    kind: str
    status: str
    description: str | None
    tags: list[Any]
    current_version_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    current_version: AssetVersionOut | None = None
    versions: list[AssetVersionOut] = Field(default_factory=list)


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    kind: str | None = Field(default=None, pattern="^(logo|image|pdf|brand_guide|svg|font|reference|other)$")
    description: str | None = Field(default=None, max_length=2000)
    tags: list[str] | None = None


class ArtifactVersionOut(ORMModel):
    id: uuid.UUID
    version_number: int
    run_id: uuid.UUID | None
    node_run_id: uuid.UUID | None
    produced_by_agent_version_id: uuid.UUID | None
    filename: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str
    width: int | None
    height: int | None
    dpi: int | None
    metadata_json: dict[str, Any]
    created_at: datetime


class ArtifactOut(ORMModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    conversation_id: uuid.UUID | None
    name: str
    type: str
    status: str
    parent_artifact_id: uuid.UUID | None
    current_version_id: uuid.UUID | None
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    current_version: ArtifactVersionOut | None = None
    versions: list[ArtifactVersionOut] = Field(default_factory=list)
    producer_agent_slug: str | None = None


class ArtifactStatusUpdate(BaseModel):
    status: str = Field(pattern="^(draft|generated|qc_failed|approved|final|archived)$")


class DownloadOut(BaseModel):
    url: str
    expires_in: int
    filename: str
    mime_type: str


class LineageNode(BaseModel):
    artifact: ArtifactOut
    children: list[LineageNode] = Field(default_factory=list)
