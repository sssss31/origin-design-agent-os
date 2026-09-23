import type { EventType, NodeState, RunState, SafeEventPayload } from "@/types/events";

export interface ActiveAgentOut {
  id: string;
  name: string;
  slug: string;
  command: string;
}

export interface AgentMemoryOut {
  agent_id: string;
  agent_name: string;
  command: string;
  turns: number;
  chars: number;
  model: string;
  updated_at: string;
}

export interface ConversationOut {
  id: string;
  project_id: string;
  title: string;
  status: "active" | "archived";
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
  active_agent: ActiveAgentOut | null;
  memory: AgentMemoryOut[];
}

export interface AttachmentOut {
  asset_id?: string | null;
  artifact_id?: string | null;
  name?: string | null;
  mime_type?: string | null;
}

export interface MessageOut {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  command: string | null;
  agent_id: string | null;
  agent_version_id: string | null;
  run_id: string | null;
  author_user_id: string | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
  attachments: AttachmentOut[];
  agent_name: string | null;
  agent_command: string | null;
}

export interface AssetVersionOut {
  id: string;
  version: number;
  filename: string;
  mime_type: string;
  size_bytes: number;
  checksum_sha256: string;
  width: number | null;
  height: number | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
}

export interface AssetOut {
  id: string;
  project_id: string;
  name: string;
  kind: string;
  status: "pending" | "ready" | "failed";
  description: string | null;
  tags: string[];
  current_version_id: string | null;
  created_at: string;
  updated_at: string;
  current_version: AssetVersionOut | null;
  versions: AssetVersionOut[];
}

export interface ArtifactVersionOut {
  id: string;
  version_number: number;
  run_id: string | null;
  node_run_id: string | null;
  produced_by_agent_version_id: string | null;
  filename: string;
  mime_type: string;
  size_bytes: number;
  checksum_sha256: string;
  width: number | null;
  height: number | null;
  dpi: number | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
}

export type ArtifactStatus = "draft" | "generated" | "qc_failed" | "approved" | "final" | "archived";

export interface ArtifactOut {
  id: string;
  workspace_id: string;
  project_id: string;
  conversation_id: string | null;
  name: string;
  type: string;
  status: ArtifactStatus;
  parent_artifact_id: string | null;
  current_version_id: string | null;
  approved_by: string | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
  current_version: ArtifactVersionOut | null;
  versions: ArtifactVersionOut[];
  producer_agent_slug: string | null;
}

export interface LineageNode {
  artifact: ArtifactOut;
  children: LineageNode[];
}

export interface DownloadOut {
  url: string;
  expires_in: number;
  filename: string;
  mime_type: string;
}

export interface NodeRunOut {
  id: string;
  node_id: string;
  index: number;
  name: string;
  kind: string;
  status: NodeState;
  agent_id: string | null;
  agent_version_id: string | null;
  output_json: Record<string, unknown>;
  error_json: { code?: string; message?: string; retryable?: boolean } | null;
  question: string | null;
  question_schema: Record<string, unknown> | null;
  answer: string | null;
  attempt: number;
  started_at: string | null;
  finished_at: string | null;
}

export interface RunOut {
  id: string;
  conversation_id: string;
  project_id: string;
  message_id: string | null;
  status: RunState;
  command: string | null;
  user_input: string;
  entry_agent_id: string | null;
  result_json: Record<string, unknown>;
  error_json: { code?: string; message?: string; retryable?: boolean } | null;
  cancel_requested: boolean;
  attempt: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  nodes: NodeRunOut[];
  event_stream_url: string;
}

export interface RunCreated {
  run_id: string;
  status: RunState;
  event_stream_url: string;
  message_id: string | null;
}

export interface EventOut {
  run_id: string;
  sequence_no: number;
  type: EventType;
  occurred_at: string;
  node_run_id: string | null;
  payload: SafeEventPayload;
}
