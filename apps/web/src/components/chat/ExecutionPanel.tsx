"use client";

import { useState } from "react";
import { ArtifactCard } from "@/components/chat/ArtifactCard";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Card";
import type { Timeline } from "@/lib/timeline";
import type { EventOut } from "@/types/chat";

const nodeIcon: Record<string, string> = { PENDING: "○", RUNNING: "◐", SUCCEEDED: "✓", FAILED: "✕", WAITING_FOR_USER: "?", SKIPPED: "–" };
const runTone: Record<string, "neutral" | "accent" | "success" | "warning" | "danger"> = { QUEUED: "neutral", RUNNING: "accent", WAITING_FOR_USER: "warning", SUCCEEDED: "success", FAILED: "danger", CANCELLED: "neutral" };

export function ExecutionPanel({ runId, timeline, events, onAnswer, onCancel, onRetry, open, onClose }: { runId: string | null; timeline: Timeline | null; events: EventOut[]; onAnswer: (answer: string) => Promise<void>; onCancel: () => Promise<void>; onRetry: () => Promise<void>; open?: boolean; onClose?: () => void }) {
  const [answer, setAnswer] = useState("");
  const [trace, setTrace] = useState(false);
  const shell = `${open ? "fixed inset-y-0 right-0 z-40 flex w-80 shadow-card" : "hidden"} xl:static xl:flex xl:w-80 xl:shadow-none shrink-0 flex-col border-l border-border bg-surface`;
  if (!runId || !timeline) {
    return (
      <aside className={`${shell} p-3 text-xs text-muted`}>
        {onClose ? <button onClick={onClose} className="mb-2 self-end text-[11px] text-muted xl:hidden">Close</button> : null}
        <p className="mb-1 text-sm font-semibold text-text">Execution</p>
        Send a command to see the node-by-node timeline here. It is rebuilt from persisted events, so refreshing never loses it.
      </aside>
    );
  }
  const q = timeline.pendingQuestion;
  return (
    <aside className={shell}>
      <div className="flex items-center justify-between border-b border-border p-3">
        <div>
          <p className="text-sm font-semibold">Run {runId.slice(0, 8)}</p>
          <Badge tone={runTone[timeline.runStatus] ?? "neutral"}>{timeline.runStatus}</Badge>
        </div>
        <div className="flex gap-1">
          {!timeline.terminal ? <Button variant="secondary" className="px-2 py-1 text-[11px]" onClick={() => void onCancel()}>Cancel</Button> : null}
          {timeline.runStatus === "FAILED" ? <Button variant="secondary" className="px-2 py-1 text-[11px]" onClick={() => void onRetry()}>Retry</Button> : null}
          <Button variant="ghost" className="px-2 py-1 text-[11px]" onClick={() => setTrace((t) => !t)}>{trace ? "Nodes" : "Trace"}</Button>
          {onClose ? <Button variant="ghost" className="px-2 py-1 text-[11px] xl:hidden" onClick={onClose}>Close</Button> : null}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-3">
        {trace ? (
          <ol className="space-y-1 text-[11px]">
            {events.map((e) => (
              <li key={e.sequence_no} className="rounded bg-surface-2 px-2 py-1">
                <span className="font-mono text-muted">#{e.sequence_no}</span> <span className="font-medium">{e.type}</span>
                {e.payload.node_name ? <span className="text-muted"> · {e.payload.node_name}</span> : null}
                {e.payload.tool_slug ? <span className="text-muted"> · {e.payload.tool_slug}</span> : null}
                {e.payload.duration_ms != null ? <span className="text-muted"> · {e.payload.duration_ms} ms</span> : null}
                {e.payload.error_message ? <span className="block text-danger">{e.payload.error_message}</span> : null}
                {e.payload.output_summary ? <span className="block text-muted">{e.payload.output_summary}</span> : null}
                {e.payload.input_summary ? <span className="block text-muted">in: {e.payload.input_summary}</span> : null}
              </li>
            ))}
          </ol>
        ) : (
          <ol className="space-y-2">
            {timeline.nodes.map((n) => (
              <li key={n.id} className="rounded-md border border-border p-2 text-xs">
                <div className="flex items-center gap-2">
                  <span className={`w-4 text-center ${n.status === "FAILED" ? "text-danger" : n.status === "SUCCEEDED" ? "text-success" : n.status === "RUNNING" ? "animate-pulse text-accent" : "text-muted"}`}>{nodeIcon[n.status]}</span>
                  <span className="font-medium">{n.name}</span>
                  {n.agent ? <span className="font-mono text-[10px] text-muted">{n.agent}</span> : null}
                  <span className="ml-auto text-[10px] text-muted">{n.durationMs != null ? `${n.durationMs} ms` : n.status.toLowerCase()}</span>
                </div>
                {n.contextSources?.length ? <p className="mt-1 text-[10px] text-muted">context: {n.contextSources.join(", ")}</p> : null}
                {n.tools.length ? <p className="mt-1 text-[10px] text-muted">tools: {n.tools.join(", ")}</p> : null}
                {n.qcPassed != null ? <p className={`mt-1 text-[10px] ${n.qcPassed ? "text-success" : "text-danger"}`}>QC {n.qcPassed ? "passed" : "failed"}</p> : null}
                {n.error ? <p className="mt-1 text-[10px] text-danger">{n.error}</p> : null}
                {n.outputSummary ? <p className="mt-1 text-[10px] text-muted">{n.outputSummary}</p> : null}
              </li>
            ))}
          </ol>
        )}
        {timeline.error ? <p className="mt-2 text-xs text-danger">{timeline.error}</p> : null}
        {timeline.artifactIds.length ? (
          <div className="mt-3 space-y-2">
            <p className="text-xs font-medium">Artifacts</p>
            {[...new Set(timeline.artifactIds)].map((id) => <ArtifactCard key={id} artifactId={id} compact />)}
          </div>
        ) : null}
      </div>
      {q ? (
        <div className="border-t border-border bg-warning/10 p-3">
          <p className="text-xs font-semibold">The agent needs one thing from you</p>
          <p className="my-1 text-sm">{q.question}</p>
          {Array.isArray((q.schema as { enum?: string[] } | null)?.enum) ? (
            <div className="mb-2 flex flex-wrap gap-1">
              {((q.schema as { enum: string[] }).enum).map((o) => <Button key={o} variant="secondary" className="px-2 py-0.5 text-[11px]" onClick={() => setAnswer(o)}>{o}</Button>)}
            </div>
          ) : null}
          <div className="flex gap-2">
            <input className="flex-1 rounded-md border border-border bg-surface px-2 py-1 text-sm" value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Your answer" onKeyDown={(e) => { if (e.key === "Enter" && answer.trim()) { void onAnswer(answer); setAnswer(""); } }} />
            <Button disabled={!answer.trim()} onClick={() => { void onAnswer(answer); setAnswer(""); }}>Reply</Button>
          </div>
        </div>
      ) : null}
    </aside>
  );
}
