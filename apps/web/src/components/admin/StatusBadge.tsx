import { Badge } from "@/components/ui/Card";
import type { AgentSummaryOut } from "@/types/admin";

export function ConnectionBadge({ agent }: { agent: AgentSummaryOut }) {
  const c = agent.connection;
  if (!c || c.connection_type === "origin") return <Badge>Origin-hosted</Badge>;
  if (!c.configured) return <Badge tone="warning">No API key</Badge>;
  if (c.connection_status === "ok") return <Badge tone="success">Connected</Badge>;
  if (c.connection_status === "error") return <Badge tone="danger">Failing</Badge>;
  return <Badge>Untested</Badge>;
}

export function RunBadge({ status }: { status: string }) {
  const tone = status === "SUCCEEDED" ? "success" : status === "FAILED" ? "danger" : status === "CANCELLED" ? "neutral" : "warning";
  return <Badge tone={tone}>{status.toLowerCase()}</Badge>;
}

export function typeLabel(type: string | undefined): string {
  return type === "openai_responses" ? "OpenAI" : type === "chatgpt_workspace" ? "ChatGPT agent" : type === "http" ? "HTTP" : "Origin";
}

/** Which runtime answers inside Origin (execution brief §3). */
export function RuntimeBadge({ agent }: { agent: AgentSummaryOut }) {
  const c = agent.connection;
  if (!c || c.connection_type !== "chatgpt_workspace") return null;
  return agent.runtime?.execution_mode === "origin_native" ? <Badge tone="accent">Origin Native</Badge> : <Badge tone="warning">Workspace Trigger</Badge>;
}
