import type { EventOut } from "@/types/chat";
import type { NodeState, RunState } from "@/types/events";

export interface TimelineNode {
  id: string;
  name: string;
  index: number;
  status: NodeState;
  agent?: string | null;
  tools: string[];
  artifacts: string[];
  durationMs?: number | null;
  error?: string | null;
  outputSummary?: string | null;
  contextSources?: string[] | null;
  qcPassed?: boolean | null;
}

export interface Timeline {
  runStatus: RunState | "QUEUED";
  nodes: TimelineNode[];
  artifactIds: string[];
  pendingQuestion: { nodeId: string; question: string; schema?: Record<string, unknown> | null } | null;
  terminal: boolean;
  lastSequence: number;
  error?: string | null;
}

/** Pure projection: the UI never trusts anything but persisted events (spec §14). */
export function deriveTimeline(events: EventOut[]): Timeline {
  const nodes = new Map<string, TimelineNode>();
  let runStatus: Timeline["runStatus"] = "QUEUED";
  let pendingQuestion: Timeline["pendingQuestion"] = null;
  let terminal = false;
  let error: string | null = null;
  const artifactIds: string[] = [];
  let last = 0;
  const node = (id: string, name?: string | null, index?: number | null): TimelineNode => {
    let n = nodes.get(id);
    if (!n) {
      n = { id, name: name ?? id, index: index ?? nodes.size, status: "PENDING", tools: [], artifacts: [] };
      nodes.set(id, n);
    }
    return n;
  };
  for (const e of events) {
    last = Math.max(last, e.sequence_no);
    const p = e.payload;
    switch (e.type) {
      case "run.started":
        runStatus = "RUNNING";
        break;
      case "node.started":
        if (p.node_id) node(p.node_id, p.node_name, p.node_index).status = "RUNNING";
        break;
      case "context.loaded":
        if (p.node_id) node(p.node_id).contextSources = p.context_sources ?? null;
        break;
      case "agent.started":
        if (p.node_id) node(p.node_id).agent = p.agent_slug ?? null;
        break;
      case "tool.started":
        if (p.node_id && p.tool_slug) node(p.node_id).tools.push(p.tool_slug);
        break;
      case "artifact.created":
        if (p.artifact_id) {
          artifactIds.push(p.artifact_id);
          if (p.node_id) node(p.node_id).artifacts.push(p.artifact_id);
        }
        break;
      case "clarification.requested":
        if (p.node_id) {
          const n = node(p.node_id);
          n.status = "WAITING_FOR_USER";
          pendingQuestion = { nodeId: p.node_id, question: p.question ?? "", schema: p.question_schema ?? null };
        }
        runStatus = "WAITING_FOR_USER";
        break;
      case "clarification.received":
        pendingQuestion = null;
        runStatus = "QUEUED";
        if (p.node_id) node(p.node_id).status = "RUNNING";
        break;
      case "node.completed":
        if (p.node_id) {
          const n = node(p.node_id);
          n.status = "SUCCEEDED";
          n.durationMs = p.duration_ms ?? null;
          n.outputSummary = p.output_summary ?? null;
          n.qcPassed = p.qc_passed ?? null;
        }
        break;
      case "node.failed":
        if (p.node_id) {
          const n = node(p.node_id);
          n.status = "FAILED";
          n.error = p.error_message ?? p.error_code ?? "failed";
        }
        break;
      case "run.completed":
        runStatus = "SUCCEEDED";
        terminal = true;
        break;
      case "run.failed":
        runStatus = "FAILED";
        terminal = true;
        error = p.error_message ?? p.error_code ?? "run failed";
        break;
      case "run.cancelled":
        runStatus = "CANCELLED";
        terminal = true;
        for (const n of nodes.values()) if (n.status === "PENDING" || n.status === "WAITING_FOR_USER") n.status = "SKIPPED";
        break;
      default:
        break;
    }
  }
  return { runStatus, nodes: [...nodes.values()].sort((a, b) => a.index - b.index), artifactIds, pendingQuestion, terminal, lastSequence: last, error };
}
