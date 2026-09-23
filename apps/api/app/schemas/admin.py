"""Admin configuration schemas (providers, tools, skills, agents). Secrets are write-only."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.domain.slash import is_valid_command, normalize_command
from app.schemas.common import ORMModel

Slug = Field(default=None, pattern=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$", max_length=80)
Status = Literal["draft", "active", "disabled"]


# ----------------------------------------------------------------------------- providers
Environment = Literal["production", "staging", "development"]


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    slug: str | None = Slug
    type: Literal["openai", "echo"] = "openai"
    environment: Environment = "production"
    base_url: str | None = Field(default=None, max_length=300)
    default_model: str | None = Field(default=None, max_length=120)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    rate_limit_policy: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    environment: Environment | None = None
    base_url: str | None = Field(default=None, max_length=300)
    default_model: str | None = Field(default=None, max_length=120)
    metadata_json: dict[str, Any] | None = None
    rate_limit_policy: dict[str, Any] | None = None
    enabled: bool | None = None


class ProviderSecretIn(BaseModel):
    """Write-only. The value is stored through SecretStore and never returned.

    A pasted cURL is accepted too: the Bearer token is extracted server-side (spec: one paste).
    """

    api_key: str = Field(min_length=8, max_length=50_000)


class ProviderCurlIn(BaseModel):
    curl: str = Field(min_length=8, max_length=50_000)
    name: str | None = Field(default=None, max_length=160)
    environment: Environment = "production"
    set_default: bool = True


class ProviderCurlPreview(BaseModel):
    provider_type: str
    base_url: str
    endpoint_kind: str
    has_key: bool
    key_placeholder: bool
    key_preview: str | None
    model: str | None
    instructions: str | None
    sample_input: str | None
    model_settings: dict[str, Any]
    has_output_schema: bool
    prompt_id: str | None
    tools: list[str]
    warnings: list[str]
    summary: dict[str, Any]


class ProviderImportOut(BaseModel):
    provider: ProviderOut
    detected: ProviderCurlPreview
    connection: ProviderConnectionOut | None = None
    created: bool


class AgentCurlImportIn(BaseModel):
    """One paste → provider key + model + agent (spec: 'the curl api of the agent')."""

    curl: str = Field(min_length=8, max_length=50_000)
    name: str = Field(min_length=1, max_length=160)
    command: str = Field(min_length=2, max_length=41)
    description: str = ""
    instructions: str | None = Field(
        default=None, description="override/complete the instructions found in the cURL"
    )
    publish: bool = True

    @field_validator("command")
    @classmethod
    def _command(cls, v: str) -> str:
        v = normalize_command(v)
        if not is_valid_command(v):
            raise ValueError("command must look like /resize (lowercase letters, digits, - or _)")
        return v


class AgentImportOut(BaseModel):
    agent: AgentOut
    provider: ProviderOut
    detected: ProviderCurlPreview
    published: bool
    connection: ProviderConnectionOut | None = None


class ProviderModelIn(BaseModel):
    model: str = Field(min_length=1, max_length=120)
    display_name: str | None = Field(default=None, max_length=160)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ProviderModelsSet(BaseModel):
    models: list[ProviderModelIn]
    default_model: str | None = None


class ProviderModelOut(ORMModel):
    id: uuid.UUID
    model: str
    display_name: str | None
    capabilities: dict[str, Any]
    resolved_capabilities: dict[str, Any] = Field(default_factory=dict)
    enabled: bool


class ProviderOut(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    slug: str
    type: str
    base_url: str | None
    has_secret: bool
    configured: bool
    is_default: bool = False
    secret_fingerprint: str | None
    key_preview: str | None
    environment: str
    metadata_json: dict[str, Any]
    enabled: bool
    default_model: str | None
    rate_limit_policy: dict[str, Any]
    health_status: str
    health_message: str | None
    last_tested_at: datetime | None
    created_at: datetime
    updated_at: datetime
    models: list[ProviderModelOut] = Field(default_factory=list)


class ProviderStatusOut(BaseModel):
    """Spec §2 contract: never more than a masked preview."""

    provider: str
    provider_id: uuid.UUID | None
    name: str | None
    configured: bool
    key_preview: str | None
    status: str
    environment: str | None
    enabled: bool
    last_tested_at: datetime | None
    models: list[str] = Field(default_factory=list)
    used_by: list[str] = Field(default_factory=list)


class ProviderConnectionOut(BaseModel):
    """Spec §3 contract for POST /admin/providers/openai/test."""

    success: bool
    provider: str
    status: Literal["connected", "failed", "not_configured"]
    message: str
    latency_ms: int
    available_models: list[str] = Field(default_factory=list)
    tested_at: datetime


class ProviderTestOut(BaseModel):
    ok: bool
    message: str
    latency_ms: int
    available_models: list[str] = Field(default_factory=list)
    tested_at: datetime


# ----------------------------------------------------------------------------- tools
ExecutorType = Literal["internal_function", "http_api", "mcp", "sandbox"]


class ToolCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$", max_length=80)
    display_name: str = Field(min_length=1, max_length=160)
    description: str = ""
    executor_type: ExecutorType = "http_api"
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    output_schema: dict[str, Any] | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=60, ge=1, le=3600)
    status: Literal["active", "disabled"] = "active"


class ToolUpdate(BaseModel):
    """Any schema/config change creates a new tool version; metadata changes do not."""

    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    status: Literal["active", "disabled"] | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    change_note: str | None = None


class ToolSecretIn(BaseModel):
    secret: str = Field(min_length=1, max_length=4096)


class ToolPermissionIn(BaseModel):
    subject_type: Literal["role", "workspace"]
    subject_key: str = Field(min_length=1, max_length=64)
    allowed: bool = True
    limits_json: dict[str, Any] = Field(default_factory=dict)


class ToolPermissionOut(ORMModel):
    id: uuid.UUID
    subject_type: str
    subject_key: str
    allowed: bool
    limits_json: dict[str, Any]


class ToolVersionOut(ORMModel):
    id: uuid.UUID
    version: int
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    config: dict[str, Any]
    timeout_seconds: int
    has_secret: bool
    published_at: datetime | None
    change_note: str | None
    created_at: datetime


class ToolOut(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    slug: str
    display_name: str
    description: str
    executor_type: str
    status: str
    is_builtin: bool
    active_version_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    active_version: ToolVersionOut | None = None
    permissions: list[ToolPermissionOut] = Field(default_factory=list)


# ----------------------------------------------------------------------------- skills
class SkillVersionInput(BaseModel):
    instructions: str | None = None
    variables_schema: dict[str, Any] | None = None
    variables_defaults: dict[str, Any] | None = None
    tool_requirements: list[str] | None = None
    default_priority: int | None = Field(default=None, ge=0, le=10000)
    change_note: str | None = None


class SkillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    slug: str | None = Slug
    description: str = ""
    scope: Literal["global", "organization", "workspace"] = "organization"
    workspace_id: uuid.UUID | None = None
    version: SkillVersionInput = Field(default_factory=SkillVersionInput)


class SkillUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    scope: Literal["global", "organization", "workspace"] | None = None
    workspace_id: uuid.UUID | None = None
    status: Literal["active", "disabled"] | None = None


class SkillFileOut(ORMModel):
    id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str
    description: str | None
    created_at: datetime


class SkillVersionOut(ORMModel):
    id: uuid.UUID
    version: int
    instructions: str
    variables_schema: dict[str, Any]
    variables_defaults: dict[str, Any]
    tool_requirements: list[str]
    default_priority: int
    published_at: datetime | None
    change_note: str | None
    created_at: datetime
    files: list[SkillFileOut] = Field(default_factory=list)


class SkillOut(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    slug: str
    description: str
    status: str
    scope: str
    workspace_id: uuid.UUID | None
    active_version_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    active_version: SkillVersionOut | None = None
    draft_version: SkillVersionOut | None = None
    versions: list[SkillVersionOut] = Field(default_factory=list)


class PublishRequest(BaseModel):
    """Publish the current draft, or roll back to an already-published version."""

    version_id: uuid.UUID | None = None
    change_note: str | None = None


# ----------------------------------------------------------------------------- agents
class AgentVersionInput(BaseModel):
    provider_id: uuid.UUID | None = None
    model: str | None = Field(default=None, max_length=120)
    instructions: str | None = None
    handoff_description: str | None = None
    model_settings: dict[str, Any] | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    can_ask_clarification: bool | None = None
    max_steps: int | None = Field(default=None, ge=1, le=500)
    timeout_seconds: int | None = Field(default=None, ge=1, le=7200)
    change_note: str | None = None


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    slug: str | None = Slug
    command: str = Field(min_length=2, max_length=41)
    description: str = ""
    is_manager: bool = False
    version: AgentVersionInput = Field(default_factory=AgentVersionInput)

    @field_validator("command")
    @classmethod
    def _command(cls, v: str) -> str:
        v = normalize_command(v)
        if not is_valid_command(v):
            raise ValueError("command must look like /resize (lowercase letters, digits, - or _)")
        return v


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    command: str | None = Field(default=None, min_length=2, max_length=41)
    description: str | None = None
    is_manager: bool | None = None
    status: Literal["active", "disabled"] | None = None

    @field_validator("command")
    @classmethod
    def _command(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = normalize_command(v)
        if not is_valid_command(v):
            raise ValueError("command must look like /resize")
        return v


class SkillBindingIn(BaseModel):
    priority: int | None = Field(default=None, ge=0, le=10000)
    skill_version_id: uuid.UUID | None = Field(
        default=None, description="pin; null follows the active version"
    )
    enabled: bool = True
    variables: dict[str, Any] = Field(default_factory=dict)


class SkillOrderIn(BaseModel):
    """Ordered skill ids; priorities are rewritten 10, 20, 30… on the draft."""

    skill_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class SkillTestRequest(BaseModel):
    agent_id: uuid.UUID
    input: str = Field(min_length=1, max_length=20000)
    use_draft: bool = True
    variables: dict[str, Any] = Field(default_factory=dict)


class ToolBindingIn(BaseModel):
    enabled: bool = True
    settings_json: dict[str, Any] = Field(default_factory=dict)
    max_calls_per_run: int | None = Field(default=None, ge=1, le=1000)


class HandoffIn(BaseModel):
    routing_hint: str = ""
    is_failure_route: bool = False


class SkillBindingOut(ORMModel):
    id: uuid.UUID
    skill_id: uuid.UUID
    skill_version_id: uuid.UUID | None
    priority: int
    enabled: bool
    variables: dict[str, Any]
    skill_name: str | None = None
    skill_slug: str | None = None


class ToolBindingOut(ORMModel):
    id: uuid.UUID
    tool_id: uuid.UUID
    enabled: bool
    settings_json: dict[str, Any]
    max_calls_per_run: int | None
    tool_slug: str | None = None
    tool_display_name: str | None = None


class HandoffOut(ORMModel):
    id: uuid.UUID
    target_agent_id: uuid.UUID
    routing_hint: str
    is_failure_route: bool
    target_agent_name: str | None = None
    target_agent_command: str | None = None


class AgentVersionOut(ORMModel):
    id: uuid.UUID
    version: int
    published_at: datetime | None
    provider_id: uuid.UUID | None
    model: str | None
    instructions: str
    handoff_description: str
    model_settings: dict[str, Any]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    can_ask_clarification: bool
    max_steps: int
    timeout_seconds: int
    change_note: str | None
    created_at: datetime
    skills: list[SkillBindingOut] = Field(default_factory=list)
    tools: list[ToolBindingOut] = Field(default_factory=list)
    handoffs: list[HandoffOut] = Field(default_factory=list)


ConnectionType = Literal["origin", "openai_responses", "http"]


class AgentConnectionIn(BaseModel):
    """Workspace V0 §3/§27: the basic connection an admin edits. The key is write-only."""

    connection_type: ConnectionType
    api_endpoint: str | None = Field(default=None, max_length=2000)
    api_key: str | None = Field(
        default=None, min_length=8, max_length=50_000, description="write-only; omit to keep"
    )
    config: dict[str, Any] = Field(default_factory=dict)
    clear_api_key: bool = False

    @field_validator("api_endpoint")
    @classmethod
    def _endpoint(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        if v and not v.lower().startswith(("https://", "http://")):
            raise ValueError("endpoint must be an absolute http(s) URL")
        return v or None


class AgentConnectionOut(BaseModel):
    connection_type: str
    api_endpoint: str | None
    configured: bool
    api_key_preview: str | None
    config: dict[str, Any]
    connection_status: str
    connection_message: str | None
    connection_tested_at: datetime | None


class AgentSummaryOut(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    slug: str
    command: str
    description: str
    status: str
    is_manager: bool
    active_version_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    active_version_number: int | None = None
    has_draft: bool = False
    model: str | None = None
    connection: AgentConnectionOut | None = None


class AgentOut(AgentSummaryOut):
    active_version: AgentVersionOut | None = None
    draft_version: AgentVersionOut | None = None
    versions: list[AgentVersionOut] = Field(default_factory=list)


class AgentTestRequest(BaseModel):
    input: str = Field(min_length=1, max_length=20000)
    use_draft: bool = True
    project_id: uuid.UUID | None = None


class TestStep(BaseModel):
    label: str
    status: Literal["done", "running", "failed", "skipped"]
    detail: str | None = None


class TestUsage(BaseModel):
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    tool_calls: int = 0
    estimated_cost_usd: float = 0.0
    priced: bool = False
    attempts: int = 1


class AgentTestOut(BaseModel):
    """Safe trace only: no reasoning, no provider payloads."""

    steps: list[TestStep] = Field(default_factory=list)
    usage: TestUsage = Field(default_factory=TestUsage)
    error_code: str | None = None
    error_message: str | None = None
    agent_slug: str
    version: int
    provider_type: str
    model: str
    runner: str
    output_text: str
    structured_output: dict[str, Any] | None
    requires_clarification: bool
    question: str | None
    defaults_used: list[str]
    steps_count: int
    instruction_sections: list[str]
    instruction_chars: int
    tools: list[str]
    duration_ms: int


class CommandOut(BaseModel):
    """What the composer autocomplete needs (spec §14)."""

    agent_id: uuid.UUID
    name: str
    slug: str
    command: str
    description: str
    is_manager: bool
