"use client";

import { ArrowUp, ChevronDown, Paperclip, Square, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { matchAgents, parseSlash } from "@/lib/slash";
import type { CommandOut } from "@/types/admin";

const ACCEPT = "image/png,image/jpeg,image/webp,image/svg+xml,application/pdf,.docx";

/**
 * One selection path for both the "/" palette and the agent dropdown: `onSelect(command)`.
 * "/resize" alone selects; "/resize text" sends "text" to that agent; plain text goes to the
 * active agent. Nothing here ever clears the conversation.
 */
export function Composer({
  agents,
  activeAgent,
  busy,
  autoFocus,
  onSend,
  onSelect,
  onStop,
}: {
  agents: CommandOut[];
  activeAgent: { name: string; command: string } | null;
  busy: boolean;
  autoFocus?: boolean;
  onSend: (content: string, files: File[]) => Promise<void>;
  onSelect: (command: string) => Promise<void>;
  onStop?: () => void;
}) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [agentMenu, setAgentMenu] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const [hint, setHint] = useState<string | null>(null);
  const ref = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus]);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [text]);

  // command palette while the first token is being typed ("/", "/re", …)
  const typing = /^\/[a-z0-9_-]*$/i.exec(text.trimStart());
  const palette = useMemo(() => (typing ? matchAgents(typing[0], agents) : []), [typing, agents]);
  const current = agents.find((a) => a.command === activeAgent?.command) ?? null;

  const pick = (a: CommandOut) => {
    setText(`${a.command} `);
    setHighlight(0);
    ref.current?.focus();
  };
  const submit = async () => {
    const body = text.trim();
    if (!body || busy) return;
    setHint(null);
    const intent = parseSlash(body, agents);
    if (intent.kind === "unknown") {
      const tips = intent.suggestions.map((s) => s.command).join(", ");
      setHint(`Unknown command ${intent.command}.${tips ? ` Did you mean ${tips}?` : ""} Type / to see all agents.`);
      return;
    }
    if (intent.kind === "select") {
      setText("");
      await onSelect(intent.command);
      ref.current?.focus();
      return;
    }
    if (intent.kind === "plain" && !activeAgent && agents.length) {
      setHint("Choose an agent first: type / or use the agent menu.");
      return;
    }
    setText("");
    const selected = files;
    setFiles([]);
    await onSend(intent.kind === "send" ? `${intent.command} ${intent.body}` : intent.text, selected);
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-4">
      <div className="relative rounded-2xl border border-border bg-surface shadow-[var(--shadow)] focus-within:border-border-strong">
        {palette.length ? (
          <div role="listbox" aria-label="Agents" className="absolute bottom-full left-0 right-0 mb-2 max-h-72 overflow-y-auto rounded-xl border border-border bg-surface p-1 shadow-lg">
            <p className="px-3 pb-1 pt-1.5 text-[11px] font-medium uppercase tracking-wide text-faint">Agents</p>
            {palette.map((a, i) => (
              <button key={a.command} role="option" aria-selected={i === highlight} onMouseDown={(e) => { e.preventDefault(); pick(a as CommandOut); }} className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm ${i === highlight ? "bg-surface-2" : "hover:bg-surface-2"}`}>
                <span className="font-mono text-accent">{a.command}</span>
                <span className="font-medium">{a.name}</span>
                <span className="truncate text-xs text-muted">{(a as CommandOut).description}</span>
              </button>
            ))}
          </div>
        ) : null}
        {files.length ? (
          <div className="flex flex-wrap gap-2 px-3 pt-3">
            {files.map((f, i) => (
              <span key={`${f.name}-${i}`} className="flex items-center gap-1 rounded-full bg-surface-2 px-2.5 py-1 text-xs">
                {f.name}
                <button onClick={() => setFiles(files.filter((_, j) => j !== i))} aria-label={`Remove ${f.name}`} className="text-faint hover:text-text"><X size={12} /></button>
              </span>
            ))}
          </div>
        ) : null}
        <textarea
          ref={ref}
          rows={1}
          value={text}
          placeholder={current ? `Message ${current.name}…` : "Message an agent… type / to choose one"}
          className="block w-full resize-none bg-transparent px-4 pt-4 pb-2 text-[15px] leading-6 outline-none placeholder:text-faint"
          onChange={(e) => { setText(e.target.value); setHighlight(0); setHint(null); }}
          onKeyDown={(e) => {
            if (palette.length && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
              e.preventDefault();
              setHighlight((h) => (h + (e.key === "ArrowDown" ? 1 : palette.length - 1)) % palette.length);
            } else if (palette.length && e.key === "Escape") {
              e.preventDefault();
              setText("");
            } else if (palette.length && (e.key === "Tab" || e.key === "Enter")) {
              e.preventDefault();
              const a = palette[highlight];
              if (a) pick(a as CommandOut);
            } else if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void submit();
            }
          }}
        />
        <div className="flex items-center justify-between px-2 pb-2">
          <div className="flex items-center gap-1">
            <button type="button" onClick={() => fileRef.current?.click()} className="rounded-lg p-2 text-muted hover:bg-surface-2 hover:text-text" aria-label="Attach files"><Paperclip size={17} /></button>
            <input ref={fileRef} type="file" multiple accept={ACCEPT} className="hidden" onChange={(e) => { setFiles([...files, ...Array.from(e.target.files ?? [])]); e.target.value = ""; }} />
            <div className="relative">
              <button type="button" onClick={() => setAgentMenu((v) => !v)} aria-haspopup="listbox" aria-expanded={agentMenu} className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm text-muted hover:bg-surface-2 hover:text-text">
                {current ? (
                  <>
                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-accent-soft text-[10px] font-semibold text-accent">{current.name.slice(0, 1)}</span>
                    <span className="font-medium text-text">{current.name}</span>
                    <span className="font-mono text-xs text-accent">{current.command}</span>
                  </>
                ) : (
                  "Choose agent"
                )}
                <ChevronDown size={14} />
              </button>
              {agentMenu ? (
                <div role="listbox" className="absolute bottom-full left-0 z-20 mb-1 w-72 rounded-xl border border-border bg-surface p-1 shadow-lg">
                  {agents.length === 0 ? <p className="px-3 py-2 text-xs text-muted">No agents connected yet.</p> : null}
                  {agents.map((a) => (
                    <button key={a.agent_id} role="option" aria-selected={a.command === activeAgent?.command} onClick={() => { setAgentMenu(false); void onSelect(a.command).then(() => ref.current?.focus()); }} className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-surface-2 ${a.command === activeAgent?.command ? "bg-surface-2" : ""}`}>
                      <span className="font-medium">{a.name}</span>
                      <span className="ml-auto font-mono text-xs text-accent">{a.command}</span>
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
          {busy && onStop ? (
            <button type="button" onClick={onStop} className="flex h-8 w-8 items-center justify-center rounded-lg bg-text text-bg" aria-label="Stop"><Square size={14} /></button>
          ) : (
            <button type="button" onClick={() => void submit()} disabled={!text.trim() || busy} className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-accent-contrast disabled:opacity-30" aria-label="Send"><ArrowUp size={17} /></button>
          )}
        </div>
      </div>
      <p className={`mt-2 text-center text-[11px] ${hint ? "text-warning" : "text-faint"}`}>{hint ?? <>Type <span className="font-mono">/agent</span> to switch agents. Follow-ups stay with the current agent.</>}</p>
    </div>
  );
}
