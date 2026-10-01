"use client";

import { Check, ChevronDown, Copy, Paperclip, RotateCcw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ArtifactCard } from "@/components/chatbot/ArtifactCard";
import { Markdown } from "@/components/chatbot/Markdown";
import type { PendingMessage } from "@/components/chatbot/useConversation";
import { splitCommand } from "@/lib/slash";
import type { Timeline } from "@/lib/timeline";
import type { MessageOut } from "@/types/chat";

function UserBubble({ content, files, faded }: { content: string; files: string[]; faded?: boolean }) {
  const { command, body } = splitCommand(content);
  return (
    <div className="flex justify-end">
      <div className={`max-w-[80%] rounded-2xl bg-surface-2 px-4 py-2.5 text-[15px] leading-6 ${faded ? "opacity-70" : ""}`}>
        {command ? <span className="mr-2 inline-block rounded-md bg-accent-soft px-1.5 py-0.5 align-middle font-mono text-xs text-accent">{command}</span> : null}
        <span className="whitespace-pre-wrap">{body || (command ? "" : content)}</span>
        {files.length ? (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {files.map((f, i) => (
              <span key={i} className="flex items-center gap-1 rounded-full bg-surface px-2 py-0.5 text-[11px] text-muted"><Paperclip size={10} /> {f}</span>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** "Resize Agent selected" — a persistent, centred system event (brief §2 case A). */
function SystemEvent({ message }: { message: MessageOut }) {
  const command = (message.metadata_json.command as string | undefined) ?? message.command ?? null;
  return (
    <div className="flex justify-center">
      <span className="rounded-full border border-border bg-surface px-3 py-1 text-[11px] text-muted">
        {message.content}
        {command ? <span className="ml-1.5 font-mono text-accent">{command}</span> : null}
      </span>
    </div>
  );
}

function Avatar({ name }: { name: string }) {
  return <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-accent">{name.slice(0, 1).toUpperCase()}</span>;
}

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button onClick={() => { void navigator.clipboard?.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1500); }); }} className="flex items-center gap-1 rounded px-1.5 py-1 text-[11px] text-faint hover:bg-surface-2 hover:text-text" aria-label="Copy response">
      {done ? <Check size={12} /> : <Copy size={12} />} {done ? "Copied" : "Copy"}
    </button>
  );
}

const NODE_LABELS: Record<string, string> = {
  request: "Request received",
  select: "Agent selected",
  context: "Conversation context loaded",
  files: "Files prepared",
  save: "Response saved",
};

/**
 * Live process display (brief §8). Only what the provider or Origin's own lifecycle actually
 * reports: Origin steps come from persisted node events, provider status lines from the stream.
 * Never reasoning. Open while running, collapsed once done.
 */
function Process({ timeline, agentName, providerLines, running }: { timeline: Timeline | null; agentName: string; providerLines: string[]; running: boolean }) {
  const [open, setOpen] = useState<boolean | null>(null);
  const nodes = timeline?.nodes ?? [];
  const isOpen = open ?? running;
  const total = nodes.reduce((s, n) => s + (n.durationMs ?? 0), 0);
  const current = nodes.find((n) => n.status === "RUNNING");
  const label = (id: string, name: string) => NODE_LABELS[id] ?? (id.startsWith("gateway:") ? `${agentName} working` : name);
  const headline = timeline?.terminal
    ? timeline.runStatus === "SUCCEEDED" ? `Completed${total ? ` in ${(total / 1000).toFixed(1)}s` : ""}` : timeline.runStatus === "FAILED" ? "Failed" : "Stopped"
    : current ? label(current.id, current.name) : nodes.length ? "Working…" : `Connecting to ${agentName}…`;
  return (
    <div className="text-xs text-muted">
      <button onClick={() => setOpen(!isOpen)} className="flex items-center gap-1.5 rounded px-1 py-0.5 hover:text-text" aria-expanded={isOpen}>
        {running ? <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" /> : timeline?.runStatus === "SUCCEEDED" ? <Check size={12} className="text-success" /> : null}
        <span className="font-medium">{agentName}</span>
        <span className="text-faint">·</span>
        <span>{headline}</span>
        <ChevronDown size={12} className={`transition ${isOpen ? "rotate-180" : ""}`} />
      </button>
      {isOpen ? (
        <ul className="mt-1 space-y-0.5 border-l border-border pl-3">
          {nodes.length === 0 ? <li className="text-faint">● Request sent, waiting for the agent…</li> : null}
          {nodes.map((n) => (
            <li key={n.id} className="flex items-center gap-2">
              <span className={n.status === "SUCCEEDED" ? "text-success" : n.status === "FAILED" ? "text-danger" : n.status === "RUNNING" ? "text-accent" : "text-faint"}>{n.status === "SUCCEEDED" ? "✓" : n.status === "FAILED" ? "✕" : n.status === "RUNNING" ? "●" : "○"}</span>
              <span>{label(n.id, n.name)}</span>
              {n.durationMs != null ? <span className="text-faint">{(n.durationMs / 1000).toFixed(1)}s</span> : null}
              {n.error ? <span className="text-danger">— {n.error}</span> : null}
            </li>
          ))}
          {providerLines.map((l, i) => (
            <li key={`p-${i}`} className="flex items-center gap-2 text-faint"><span>│</span><span>{l}</span></li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function Thread({
  messages,
  pending,
  busy,
  streamText,
  timeline,
  agentName,
  error,
  onRetry,
}: {
  messages: MessageOut[];
  pending: PendingMessage | null;
  busy: boolean;
  streamText: string;
  timeline: Timeline | null;
  agentName: string;
  error: string | null;
  onRetry: () => void;
}) {
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messages.length, pending, streamText, busy, error]);
  // provider status lines (e.g. "Status: in_progress") are short single lines; real answers are longer markdown
  const providerLines = streamText.split("\n").map((l) => l.trim()).filter((l) => l && l.length < 120 && /^(Triggered|Status:|Connecting|Waiting|Processing)/.test(l));
  const answerText = providerLines.length && streamText.trim().split("\n").every((l) => providerLines.includes(l.trim()) || !l.trim()) ? "" : streamText;
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-6">
        {messages.map((m) =>
          m.role === "system" ? (
            <SystemEvent key={m.id} message={m} />
          ) : m.role === "user" ? (
            <UserBubble key={m.id} content={m.content} files={m.attachments.map((a) => a.name ?? "file")} />
          ) : (
            <div key={m.id} className="flex gap-3">
              <Avatar name={m.agent_name ?? "A"} />
              <div className="min-w-0 flex-1">
                <p className="mb-1 text-xs font-medium text-muted">{m.agent_name ?? "Agent"} {m.agent_command ? <span className="font-mono text-accent">{m.agent_command}</span> : null}</p>
                <Markdown text={m.content} />
                {m.attachments.filter((a) => a.artifact_id).map((a) => <ArtifactCard key={a.artifact_id} attachment={a} />)}
                <div className="mt-1 flex items-center gap-1">
                  <CopyButton text={m.content} />
                </div>
              </div>
            </div>
          ),
        )}
        {pending ? <UserBubble content={pending.content} files={pending.files} faded /> : null}
        {busy || streamText ? (
          <div className="flex gap-3">
            <Avatar name={agentName} />
            <div className="min-w-0 flex-1 space-y-2">
              <Process timeline={timeline} agentName={agentName} providerLines={providerLines} running={busy} />
              {answerText ? (
                <div className="stream">
                  <Markdown text={answerText} />
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
        {error ? (
          <div className="flex items-center gap-3 rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm">
            <span className="flex-1">⚠ {error}</span>
            <button onClick={onRetry} className="flex items-center gap-1 rounded-md border border-border bg-surface px-2.5 py-1 text-xs font-medium hover:bg-surface-2"><RotateCcw size={12} /> Retry</button>
          </div>
        ) : null}
        <div ref={bottom} />
      </div>
    </div>
  );
}
