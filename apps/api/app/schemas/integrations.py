"""Schemas for custom REST integrations. Secret values are write-only (never returned)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel

Method = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]


class IntegrationSecretIn(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    value: str = Field(min_length=1, max_length=8192)
    location: Literal["header", "query", "basic", "body", "cookie"] = "header"


class IntegrationSecretOut(ORMModel):
    name: str
    fingerprint: str
    key_preview: str | None
    location: str
    rotated_at: datetime | None
    created_at: datetime


class IntegrationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$", max_length=80)
    description: str = ""
    method: Method = "POST"
    endpoint: str = Field(min_length=8, max_length=2000)
    headers_template: dict[str, str] = Field(default_factory=dict)
    query_template: dict[str, str] = Field(default_factory=dict)
    body_template: str | None = Field(default=None, max_length=100_000)
    content_type: str = Field(default="application/json", max_length=120)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    max_response_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)
    secrets: list[IntegrationSecretIn] = Field(default_factory=list)
    create_tool: bool = True

    @field_validator("endpoint")
    @classmethod
    def _https(cls, v: str) -> str:
        v = v.strip()
        if not v.lower().startswith(("https://", "http://")):
            raise ValueError("endpoint must be an absolute http(s) URL")
        return v


class IntegrationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    method: Method | None = None
    endpoint: str | None = Field(default=None, min_length=8, max_length=2000)
    headers_template: dict[str, str] | None = None
    query_template: dict[str, str] | None = None
    body_template: str | None = Field(default=None, max_length=100_000)
    content_type: str | None = Field(default=None, max_length=120)
    timeout_seconds: int | None = Field(default=None, ge=1, le=300)
    max_response_bytes: int | None = Field(default=None, ge=1024, le=50 * 1024 * 1024)
    status: Literal["active", "disabled"] | None = None


class IntegrationOut(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    slug: str
    description: str
    method: str
    endpoint: str
    headers_template: dict[str, str]
    query_template: dict[str, str]
    body_template: str | None
    content_type: str
    timeout_seconds: int
    max_response_bytes: int
    status: str
    auth_summary: str
    tool_id: uuid.UUID | None
    health_status: str
    health_message: str | None
    last_tested_at: datetime | None
    request_count: int
    error_count: int
    created_at: datetime
    updated_at: datetime
    secrets: list[IntegrationSecretOut] = Field(default_factory=list)
    variables: list[str] = Field(default_factory=list)
    missing_secrets: list[str] = Field(default_factory=list)
    tool_slug: str | None = None
    used_by: list[str] = Field(default_factory=list)
    avg_latency_ms: int | None = None


class CurlParseIn(BaseModel):
    curl: str = Field(min_length=4, max_length=50_000)


class CurlPreview(BaseModel):
    """Dry-run result: templates with secret references, secret *names* only, summary rows."""

    method: str
    url: str
    headers: dict[str, str]
    query: dict[str, str]
    body: str | None
    content_type: str
    body_kind: str
    secrets: list[dict[str, str]]
    variables: list[str]
    warnings: list[str]
    summary: dict[str, str]


class CurlImportIn(CurlParseIn):
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    create_tool: bool = True


class IntegrationTestIn(BaseModel):
    variables: dict[str, Any] = Field(default_factory=dict)


class IntegrationTestOut(BaseModel):
    ok: bool
    request: dict[str, Any]
    status: int | None
    latency_ms: int
    response_size_bytes: int | None
    content_type: str | None
    response_preview: Any
    file: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    tested_at: datetime
