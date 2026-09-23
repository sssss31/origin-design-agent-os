/**
 * Execution event vocabulary. Source of truth: packages/shared-schemas/run-states.json
 * (generated from apps/api/app/domain). Update both when adding a state or event.
 */

export const RUN_STATES = ["QUEUED", "RUNNING", "WAITING_FOR_USER", "SUCCEEDED", "FAILED", "CANCELLED"] as const;
export type RunState = (typeof RUN_STATES)[number];

export const NODE_STATES = ["PENDING", "RUNNING", "SUCCEEDED", "FAILED", "WAITING_FOR_USER", "SKIPPED"] as const;
export type NodeState = (typeof NODE_STATES)[number];

export const EVENT_TYPES = [
  "run.started",
  "node.started",
  "context.loaded",
  "agent.selected",
  "files.prepared",
  "agent.started",
  "response.streaming",
  "provider.retry",
  "tool.started",
  "tool.completed",
  "artifact.created",
  "clarification.requested",
  "clarification.received",
  "node.completed",
  "node.failed",
  "run.completed",
  "run.failed",
  "run.cancelled",
  "heartbeat",
] as const;
export type EventType = (typeof EVENT_TYPES)[number];

export interface SafeEventPayload {
  node_id?: string | null;
  node_name?: string | null;
  node_index?: number | null;
  node_status?: NodeState | null;
  run_status?: RunState | null;
  agent_slug?: string | null;
  agent_name?: string | null;
  agent_version?: number | null;
  tool_slug?: string | null;
  tool_display_name?: string | null;
  input_summary?: string | null;
  output_summary?: string | null;
  artifact_id?: string | null;
  artifact_type?: string | null;
  artifact_version?: number | null;
  question?: string | null;
  question_schema?: Record<string, unknown> | null;
  defaults_used?: string[] | null;
  context_sources?: string[] | null;
  error_code?: string | null;
  error_message?: string | null;
  retryable?: boolean | null;
  duration_ms?: number | null;
  findings_count?: number | null;
  qc_passed?: boolean | null;
  delta?: string | null;
  session_native?: boolean | null;
  files_count?: number | null;
  history_messages?: number | null;
  retry_attempt?: number | null;
}

export interface ExecutionEvent {
  run_id: string;
  sequence_no: number;
  type: EventType;
  occurred_at: string;
  node_run_id?: string | null;
  payload: SafeEventPayload;
}
