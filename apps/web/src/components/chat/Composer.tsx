"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { commandsApi } from "@/lib/api/admin";
import type { CommandOut } from "@/types/admin";
import type { AssetOut } from "@/types/chat";

export function Composer({ assets, busy, onSend, onStop, activeAgent, memoryTurns, onActivate, onClearMemory }: { assets: AssetOut[]; busy: boolean; onSend: (content: string, assetIds: string[]) => Promise<void>; onStop?: () => void; activeAgent?: { name: string; command: string } | null; memoryTurns?: number; onActivate?: (command: string | null) => Promise<void>; onClearMemory?: () => Promise<void> }) {
  const [text, setText] = useState("");
  const [commands, setCommands] = useState<CommandOut[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [showAssets, setShowAssets] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    commandsApi.list().then(setCommands).catch(() => setCommands([]));
  }, []);
  const firstToken = text.split(/\s/)[0] ?? "";
  const menu = useMemo(() => (text.startsWith("/") && !text.includes(" ") ? commands.filter((c) => c.command.startsWith(firstToken.toLowerCase())) : []), [text, commands, firstToken]);
  const pick = (c: CommandOut) => {
    setText(`${c.command} `);
    setHighlight(0);
    ref.current?.focus();
  };
  const send = async () => {
    if (!text.trim() || busy) return;
    const content = text;
    const bare = /^\/[a-z][a-z0-9_-]*$/i.exec(content.trim());
    setText("");
    if (bare && onActivate) {
      // "/copy" alone: switch the conversation to that agent without starting a run
      await onActivate(bare[0].toLowerCase() === "/auto" ? null : bare[0].toLowerCase());
      return;
    }
    await onSend(content, selected);
    setSelected([]);
  };
  return (
    <div className="border-t border-border bg-surface p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px]">
        {activeAgent ? (
          <>
            <span className="rounded-full bg-accent-soft px-2 py-0.5 font-medium text-accent">Talking to {activeAgent.name} <span className="font-mono">{activeAgent.command}</span></span>
            {memoryTurns ? <span className="text-muted">remembers {memoryTurns} turn{memoryTurns === 1 ? "" : "s"}</span> : <span className="text-faint">no memory yet</span>}
            {onClearMemory && memoryTurns ? <button className="text-muted underline-offset-2 hover:underline" onClick={() => void onClearMemory()}>reset memory</button> : null}
            {onActivate ? <button className="text-muted underline-offset-2 hover:underline" onClick={() => void onActivate(null)}>back to Manager (/auto)</button> : null}
          </>
        ) : (
          <span className="text-faint">Manager routes plain messages · type /copy, /resize… to talk to one agent</span>
        )}
      </div>
      {menu.length ? (
        <div className="mb-2 rounded-md border border-border bg-surface-2 p-1" role="listbox">
          {menu.map((c, i) => (
            <button key={c.agent_id} role="option" aria-selected={i === highlight} className={`flex w-full items-center gap-2 rounded px-2 py-1 text-left text-sm ${i === highlight ? "bg-accent/15" : "hover:bg-surface"}`} onMouseDown={(e) => { e.preventDefault(); pick(c); }}>
              <span className="font-mono text-accent">{c.command}</span>
              <span className="font-medium">{c.name}</span>
              <span className="truncate text-xs text-muted">{c.description}</span>
            </button>
          ))}
        </div>
      ) : null}
      {selected.length ? <p className="mb-1 text-[11px] text-muted">Attached: {selected.map((id) => assets.find((a) => a.id === id)?.name ?? id).join(", ")}</p> : null}
      <div className="flex items-end gap-2">
        <textarea
          ref={ref}
          rows={2}
          value={text}
          placeholder={activeAgent ? `Message ${activeAgent.name}… (/auto to switch back)` : "Message or /command…"}
          className="flex-1 resize-none rounded-md border border-border bg-surface px-3 py-2 text-sm outline-none focus:border-accent"
          onChange={(e) => { setText(e.target.value); setHighlight(0); }}
          onKeyDown={(e) => {
            if (menu.length && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
              e.preventDefault();
              setHighlight((h) => (h + (e.key === "ArrowDown" ? 1 : menu.length - 1)) % menu.length);
            } else if (menu.length && (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey))) {
              e.preventDefault();
              const c = menu[highlight];
              if (c) pick(c);
            } else if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
        />
        <div className="flex flex-col gap-1">
          <Button variant="secondary" onClick={() => setShowAssets((s) => !s)} title="Attach assets">📎</Button>
          {busy && onStop ? <Button variant="danger" onClick={onStop}>Stop</Button> : <Button disabled={!text.trim() || busy} onClick={() => void send()}>Send</Button>}
        </div>
      </div>
      {showAssets ? (
        <div className="mt-2 flex flex-wrap gap-1">
          {assets.length === 0 ? <span className="text-xs text-muted">No assets uploaded yet.</span> : null}
          {assets.map((a) => (
            <label key={a.id} className="flex items-center gap-1 rounded border border-border px-2 py-0.5 text-[11px]">
              <input type="checkbox" checked={selected.includes(a.id)} onChange={(e) => setSelected(e.target.checked ? [...selected, a.id] : selected.filter((x) => x !== a.id))} /> {a.name}
            </label>
          ))}
        </div>
      ) : null}
    </div>
  );
}
