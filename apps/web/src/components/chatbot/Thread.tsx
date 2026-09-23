"use client";

import { Check, ChevronDown, Copy, Paperclip, RotateCcw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Markdown } from "@/components/chatbot/Markdown";
import type { PendingMessage } from "@/components/chatbot/useConversation";
import type { Timeline } from "@/lib/timeline";
import type { MessageOut } from "@/types/chat";

function splitCommand(content: string): { command: string | null; body: string } {
  const m = /^(\/[a-z][a-z0-9_-]*)\s*([\s\S]*)$/i.exec(content);
  return m ? { command: m[1] ?? null, body: m[2] ?? "" } : { command: null, body: content };
}

function UserBubble({ content, files, faded }: { content: string; files: string[]; faded?: boolean }) {
  const { command, body } = splitCommand(content);
  return (
    <div className="flex justify-end">
      <div className={`max-w-[80%] rounded-2xl bg-surface-2 px-4 py-2.5 text-[15px] leading-6 ${faded ? "opacity-70" : ""}`}>
        {command ? <span className="mr-2 inline-block rounded-md bg-accent-soft px-1.5 py-0.5 font-mono text-xs text-accent align-middle">{command}</span> : null}
        <span className="whitespace-pre-wrap">{body || (command ? "" : content)}</span>
        {files.length ? (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {files.map((f, i) => <span key={i} className="flex items-center gap-1 rounded-full bg-surface px-2 py-0.5 text-[11px] text-muted"><Paperclip size={10} /> {f}</span>)}
          </div>
        ) : null}
      </div>
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

function Steps({ timeline, agentName }: { timeline: Timeline | null; agentName: string }) {
  const [open, setOpen] = useState(false);
  const nodes = timeline?.nodes ?? [];
  const running = nodes.find((n) => n.status === "RUNNING");
  const label = running ? running.name : timeline?.terminal ? "Done" : `${agentName} is working`;
  return (
    <div className="text-xs text-muted">
      <button onClick={() => setOpen((v) => !v)} className="flex items-center gap-1 rounded px-1 py-0.5 hover:text-text">
        {!timeline?.terminal ? <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" /> : null}
        {label}
        <ChevronDown size={12} className={`transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open && nodes.length ? (
        <ul className="mt-1 space-y-0.5 border-l border-border pl-3">
          {nodes.map((n) => (
            <li key={n.id} className="flex items-center gap-2">
              <span className={n.status === "SUCCEEDED" ? "text-success" : n.status === "FAILED" ? "text-danger" : n.status === "RUNNING" ? "text-accent" : "text-faint"}>{n.status === "SUCCEEDED" ? "✓" : n.status === "FAILED" ? "✕" : n.status === "RUNNING" ? "•" : "○"}</span>
              <span>{n.name}</span>
              {n.durationMs != null ? <span className="text-faint">{n.durationMs} ms</span> : null}
            </li>
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
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-6">
        {messages.map((m) =>
          m.role === "user" ? (
            <UserBubble key={m.id} content={m.content} files={m.attachments.map((a) => a.name ?? "file")} />
          ) : (
            <div key={m.id} className="flex gap-3">
              <Avatar name={m.agent_name ?? "A"} />
              <div className="min-w-0 flex-1">
                <p className="mb-1 text-xs font-medium text-muted">{m.agent_name ?? "Agent"} {m.agent_command ? <span className="font-mono text-accent">{m.agent_command}</span> : null}</p>
                <Markdown text={m.content} />
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
              <Steps timeline={timeline} agentName={agentName} />
              {streamText ? (
                <div className="stream">
                  <Markdown text={streamText} />
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
        {error ? (
          <div className="flex items-center gap-3 rounded-xl border border-danger/30 bg-danger/5 px-4 py-3 text-sm">
            <span className="flex-1">{error}</span>
            <button onClick={onRetry} className="flex items-center gap-1 rounded-md border border-border bg-surface px-2.5 py-1 text-xs font-medium hover:bg-surface-2"><RotateCcw size={12} /> Retry</button>
          </div>
        ) : null}
        <div ref={bottom} />
      </div>
    </div>
  );
}
