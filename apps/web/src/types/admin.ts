/** Mirrors apps/api/app/schemas/admin.py. */

export type EntityStatus = "draft" | "active" | "disabled";

export interface ProviderModelOut {
  id: string;
  model: string;
  display_name: string | null;
  capabilities: Record<string, unknown>;
  enabled: boolean;
}

export interface ProviderOut {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  type: "openai" | "echo" | string;
  base_url: string | null;
  has_secret: boolean;
  secret_fingerprint: string | null;
  metadata_json: Record<string, unknown>;
  enabled: boolean;
  default_model: string | null;
  rate_limit_policy: Record<string, unknown>;
  health_status: "unknown" | "ok" | "error";
  health_message: string | null;
  last_tested_at: string | null;
  created_at: string;
  updated_at: string;
  models: ProviderModelOut[];
}

export interface ProviderTestOut {
  ok: boolean;
  message: string;
  latency_ms: number;
  available_models: string[];
  tested_at: string;
}

export type ExecutorType = "internal_function" | "http_api" | "mcp" | "sandbox";

export interface ToolVersionOut {
  id: string;
  version: number;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown> | null;
  config: Record<string, unknown>;
  timeout_seconds: number;
  has_secret: boolean;
  published_at: string | null;
  change_note: string | null;
  created_at: string;
}

export interface ToolPermissionOut {
  id: string;
  subject_type: "role" | "workspace";
  subject_key: string;
  allowed: boolean;
  limits_json: Record<string, unknown>;
}

export interface ToolOut {
  id: string;
  organization_id: string;
  slug: string;
  display_name: string;
  description: string;
  executor_type: ExecutorType;
  status: "active" | "disabled";
  is_builtin: boolean;
  active_version_id: string | null;
  created_at: string;
  updated_at: string;
  active_version: ToolVersionOut | null;
  permissions: ToolPermissionOut[];
}

export interface SkillFileOut {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  checksum_sha256: string;
  description: string | null;
  created_at: string;
}

export interface SkillVersionOut {
  id: string;
  version: number;
  instructions: string;
  variables_schema: Record<string, unknown>;
  variables_defaults: Record<string, unknown>;
  tool_requirements: string[];
  default_priority: number;
  published_at: string | null;
  change_note: string | null;
  created_at: string;
  files: SkillFileOut[];
}

export interface SkillOut {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  description: string;
  status: EntityStatus;
  scope: "global" | "organization" | "workspace";
  workspace_id: string | null;
  active_version_id: string | null;
  created_at: string;
  updated_at: string;
  active_version: SkillVersionOut | null;
  draft_version: SkillVersionOut | null;
  versions: SkillVersionOut[];
}

export interface SkillVersionInput {
  instructions?: string;
  variables_schema?: Record<string, unknown>;
  variables_defaults?: Record<string, unknown>;
  tool_requirements?: string[];
  default_priority?: number;
  change_note?: string;
}

export interface SkillBindingOut {
  id: string;
  skill_id: string;
  skill_version_id: string | null;
  priority: number;
  enabled: boolean;
  variables: Record<string, unknown>;
  skill_name: string | null;
  skill_slug: string | null;
}

export interface ToolBindingOut {
  id: string;
  tool_id: string;
  enabled: boolean;
  settings_json: Record<string, unknown>;
  max_calls_per_run: number | null;
  tool_slug: string | null;
  tool_display_name: string | null;
}

export interface HandoffOut {
  id: string;
  target_agent_id: string;
  routing_hint: string;
  is_failure_route: boolean;
  target_agent_name: string | null;
  target_agent_command: string | null;
}

export interface AgentVersionOut {
  id: string;
  version: number;
  published_at: string | null;
  provider_id: string | null;
  model: string | null;
  instructions: string;
  handoff_description: string;
  model_settings: Record<string, unknown>;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  can_ask_clarification: boolean;
  max_steps: number;
  timeout_seconds: number;
  change_note: string | null;
  created_at: string;
  skills: SkillBindingOut[];
  tools: ToolBindingOut[];
  handoffs: HandoffOut[];
}

export interface AgentVersionInput {
  provider_id?: string | null;
  model?: string | null;
  instructions?: string;
  handoff_description?: string;
  model_settings?: Record<string, unknown>;
  input_schema?: Record<string, unknown>;
  output_schema?: Record<string, unknown>;
  can_ask_clarification?: boolean;
  max_steps?: number;
  timeout_seconds?: number;
  change_note?: string;
}

export interface AgentSummaryOut {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  command: string;
  description: string;
  status: EntityStatus;
  is_manager: boolean;
  active_version_id: string | null;
  created_at: string;
  updated_at: string;
  active_version_number: number | null;
  has_draft: boolean;
  model: string | null;
}

export interface AgentOut extends AgentSummaryOut {
  active_version: AgentVersionOut | null;
  draft_version: AgentVersionOut | null;
  versions: AgentVersionOut[];
}

export interface AgentTestOut {
  agent_slug: string;
  version: number;
  provider_type: string;
  model: string;
  runner: string;
  output_text: string;
  structured_output: Record<string, unknown> | null;
  requires_clarification: boolean;
  question: string | null;
  defaults_used: string[];
  steps: number;
  instruction_sections: string[];
  instruction_chars: number;
  tools: string[];
  duration_ms: number;
}

export interface CommandOut {
  agent_id: string;
  name: string;
  slug: string;
  command: string;
  description: string;
  is_manager: boolean;
}
