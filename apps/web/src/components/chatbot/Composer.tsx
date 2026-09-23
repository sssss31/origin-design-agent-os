"use client";

import { ArrowUp, ChevronDown, Paperclip, Square, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { CommandOut } from "@/types/admin";

const ACCEPT = "image/png,image/jpeg,image/webp,image/svg+xml,application/pdf,.docx";

export function Composer({
  agents,
  activeAgent,
  busy,
  autoFocus,
  onSend,
  onStop,
}: {
  agents: CommandOut[];
  activeAgent: { name: string; command: string } | null;
  busy: boolean;
  autoFocus?: boolean;
  onSend: (content: string, files: File[]) => Promise<void>;
  onStop?: () => void;
}) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [chosen, setChosen] = useState<string | null>(null);
  const [agentMenu, setAgentMenu] = useState(false);
  const [highlight, setHighlight] = useState(0);
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

  const typing = /^\/[a-z0-9_-]*$/i.exec(text.trimStart());
  const menu = useMemo(() => (typing ? agents.filter((a) => a.command.startsWith(typing[0].toLowerCase())) : []), [typing, agents]);
  const currentCommand = chosen ?? activeAgent?.command ?? null;
  const current = agents.find((a) => a.command === currentCommand) ?? null;

  const pick = (a: CommandOut) => {
    setText(`${a.command} `);
    setHighlight(0);
    ref.current?.focus();
  };
  const submit = async () => {
    const body = text.trim();
    if (!body || busy) return;
    let content = body;
    if (!body.startsWith("/") && chosen && chosen !== activeAgent?.command) content = `${chosen} ${body}`;
    setText("");
    const selected = files;
    setFiles([]);
    setChosen(null);
    await onSend(content, selected);
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-4">
      <div className="relative rounded-2xl border border-border bg-surface shadow-[var(--shadow)] focus-within:border-border-strong">
        {menu.length ? (
          <div role="listbox" className="absolute bottom-full left-0 right-0 mb-2 max-h-72 overflow-y-auto rounded-xl border border-border bg-surface p-1 shadow-lg">
            {menu.map((a, i) => (
              <button key={a.agent_id} role="option" aria-selected={i === highlight} onMouseDown={(e) => { e.preventDefault(); pick(a); }} className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm ${i === highlight ? "bg-surface-2" : "hover:bg-surface-2"}`}>
                <span className="font-mono text-accent">{a.command}</span>
                <span className="font-medium">{a.name}</span>
                <span className="truncate text-xs text-muted">{a.description}</span>
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
          onChange={(e) => { setText(e.target.value); setHighlight(0); }}
          onKeyDown={(e) => {
            if (menu.length && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
              e.preventDefault();
              setHighlight((h) => (h + (e.key === "ArrowDown" ? 1 : menu.length - 1)) % menu.length);
            } else if (menu.length && (e.key === "Tab" || e.key === "Enter")) {
              e.preventDefault();
              const a = menu[highlight];
              if (a) pick(a);
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
              <button type="button" onClick={() => setAgentMenu((v) => !v)} className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm text-muted hover:bg-surface-2 hover:text-text">
                {current ? <><span className="font-medium text-text">{current.name}</span><span className="font-mono text-xs text-accent">{current.command}</span></> : "Choose agent"}
                <ChevronDown size={14} />
              </button>
              {agentMenu ? (
                <div className="absolute bottom-full left-0 z-20 mb-1 w-72 rounded-xl border border-border bg-surface p-1 shadow-lg">
                  {agents.length === 0 ? <p className="px-3 py-2 text-xs text-muted">No agents connected yet.</p> : null}
                  {agents.map((a) => (
                    <button key={a.agent_id} onClick={() => { setChosen(a.command); setAgentMenu(false); ref.current?.focus(); }} className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-surface-2 ${a.command === currentCommand ? "bg-surface-2" : ""}`}>
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
      <p className="mt-2 text-center text-[11px] text-faint">Type <span className="font-mono">/agent</span> at the start of a message to switch agents. Follow-ups stay with the current agent.</p>
    </div>
  );
}
