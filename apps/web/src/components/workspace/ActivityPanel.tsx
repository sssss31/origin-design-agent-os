"use client";

import type { Timeline } from "@/lib/timeline";
import type { EventOut } from "@/types/chat";

const ICON: Record<string, string> = { SUCCEEDED: "✓", RUNNING: "●", PENDING: "○", FAILED: "✕", SKIPPED: "–", WAITING_FOR_USER: "?" };

/** Workspace V0 §15–§16: operational nodes only, updated live from SSE. */
export function ActivityPanel({ runId, timeline, events, onRetry, onCancel }: { runId: string | null; timeline: Timeline | null; events: EventOut[]; onRetry?: () => void; onCancel?: () => void }) {
  const last = events[events.length - 1];
  const details = new Map<string, string>();
  for (const e of events) {
    const id = e.payload.node_id;
    if (!id) continue;
    if (e.type === "context.loaded") details.set(id, e.payload.session_native ? "agent's own session continued" : `${e.payload.history_messages ?? 0} recent messages`);
    if (e.type === "files.prepared") details.set(id, `${e.payload.files_count ?? 0} file(s)`);
    if (e.type === "agent.started") details.set(id, e.payload.files_count ? `${e.payload.files_count} file(s) attached` : "request sent");
    if (e.type === "response.streaming") details.set(id, "receiving response…");
    if (e.type === "node.completed" && e.payload.duration_ms != null) details.set(id, `${e.payload.duration_ms} ms`);
    if (e.type === "node.failed") details.set(id, e.payload.error_message ?? "failed");
  }
  const failed = timeline?.runStatus === "FAILED";
  const errorEvent = [...events].reverse().find((e) => e.type === "run.failed" || e.type === "node.failed");
  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-faint">Activity</p>
        <p className="text-sm font-medium">{runId ? `Request #${runId.slice(-4).toUpperCase()}` : "No request yet"}</p>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {!timeline ? <p className="text-xs text-muted">Send a message with /agent to see the steps here.</p> : (
          <ol className="space-y-2 text-sm">
            {timeline.nodes.map((n) => (
              <li key={n.id} className={`flex items-start gap-2 ${n.status === "SUCCEEDED" ? "text-success" : n.status === "RUNNING" ? "text-accent" : n.status === "FAILED" ? "text-danger" : "text-muted"}`}>
                <span className="w-4 shrink-0 font-mono">{ICON[n.status] ?? "○"}</span>
                <span>
                  <span className={n.status === "RUNNING" ? "animate-pulse" : ""}>{n.name}</span>
                  {details.get(n.id) ? <span className="block text-[11px] text-faint">{details.get(n.id)}</span> : null}
                </span>
              </li>
            ))}
          </ol>
        )}
        {failed && errorEvent ? (
          <div className="mt-4 rounded-md border border-danger/40 bg-danger/5 p-3 text-xs">
            <p className="font-medium text-danger">{errorEvent.payload.error_message ?? "The agent could not complete the request."}</p>
            {onRetry ? <button onClick={onRetry} className="mt-2 rounded-md bg-accent px-3 py-1 text-xs font-medium text-accent-contrast">Retry</button> : null}
          </div>
        ) : null}
        {timeline && !timeline.terminal && onCancel ? <button onClick={onCancel} className="mt-4 text-xs text-muted underline-offset-2 hover:underline">Stop</button> : null}
        {last && last.type !== "response.streaming" ? <p className="mt-4 text-[11px] text-faint">Last event: {last.type} · {new Date(last.occurred_at).toLocaleTimeString()}</p> : null}
      </div>
    </div>
  );
}
