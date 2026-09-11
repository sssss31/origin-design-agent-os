"use client";

import { useEffect, useRef } from "react";
import { ArtifactCard } from "@/components/chat/ArtifactCard";
import { Badge } from "@/components/ui/Card";
import type { MessageOut } from "@/types/chat";

export function ChatThread({ messages, activeRunId, onOpenRun }: { messages: MessageOut[]; activeRunId: string | null; onOpenRun: (runId: string) => void }) {
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messages.length]);
  return (
    <div className="flex-1 space-y-4 overflow-y-auto p-4">
      {messages.length === 0 ? <p className="text-center text-xs text-muted">Start with a slash command such as /resize, /qc or /auto — type “/” to see the agents available.</p> : null}
      {messages.map((m) => (
        <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
          <div className={`max-w-[75%] rounded-lg px-3 py-2 text-sm ${m.role === "user" ? "bg-accent/15" : "border border-border bg-surface"}`}>
            <div className="mb-1 flex items-center gap-2 text-[11px] text-muted">
              {m.role === "assistant" ? <Badge tone="accent">{m.agent_name ?? "assistant"}{m.agent_command ? ` ${m.agent_command}` : ""}</Badge> : m.metadata_json.clarification_answer ? <Badge tone="warning">clarification reply</Badge> : <span>you</span>}
              <span>{new Date(m.created_at).toLocaleTimeString()}</span>
              {m.run_id ? (
                <button className={`text-accent ${m.run_id === activeRunId ? "font-semibold" : ""}`} onClick={() => onOpenRun(m.run_id!)}>
                  run {m.run_id.slice(0, 8)}
                </button>
              ) : null}
            </div>
            <p className="whitespace-pre-wrap">{m.content}</p>
            {m.attachments.length ? (
              <div className="mt-2 space-y-2">
                {m.attachments.map((a, i) =>
                  a.artifact_id ? <ArtifactCard key={a.artifact_id + i} artifactId={a.artifact_id} compact /> : <span key={(a.asset_id ?? "") + i} className="inline-block rounded border border-border px-2 py-0.5 text-[11px] text-muted">📎 {a.name ?? "asset"}</span>,
                )}
              </div>
            ) : null}
          </div>
        </div>
      ))}
      <div ref={bottom} />
    </div>
  );
}
