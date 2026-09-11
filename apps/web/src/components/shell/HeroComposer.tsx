"use client";

import { ArrowUp, Paperclip, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { commandsApi } from "@/lib/api/admin";
import { assetsApi } from "@/lib/api/chat";
import { ApiError } from "@/lib/api/client";
import { dashboardApi } from "@/lib/api/dashboard";
import { RECENTS_CHANGED } from "@/components/shell/AppShell";
import type { CommandOut } from "@/types/admin";
import type { AssetOut } from "@/types/chat";

const MODES: { id: string; label: string; command: string; hint: string }[] = [
  { id: "auto", label: "Auto", command: "/auto", hint: "Let the Manager plan the specialists" },
  { id: "master", label: "Design", command: "/master", hint: "Create or revise a master design" },
  { id: "resize", label: "Resize", command: "/resize", hint: "Adapt to 4:5, 9:16, 16:9, banners" },
  { id: "editable", label: "Editable", command: "/editable", hint: "Editable SVG / layered output" },
  { id: "qc", label: "QC", command: "/qc", hint: "Check brand, layout, dimensions" },
  { id: "export", label: "Export", command: "/export", hint: "Final PNG / JPG / PDF" },
];

export function HeroComposer({ projects, defaultProjectId, autoFocus = false }: { projects: { id: string; name: string; workspace_name: string }[]; defaultProjectId?: string; autoFocus?: boolean }) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [mode, setMode] = useState("auto");
  const [projectId, setProjectId] = useState(defaultProjectId ?? "");
  const [commands, setCommands] = useState<CommandOut[]>([]);
  const [assets, setAssets] = useState<AssetOut[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [showAssets, setShowAssets] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    commandsApi.list().then(setCommands).catch(() => setCommands([]));
  }, []);
  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus]);
  useEffect(() => {
    if (!projectId) return;
    assetsApi.list(projectId).then(setAssets).catch(() => setAssets([]));
  }, [projectId]);

  const available = useMemo(() => new Set(commands.map((c) => c.command)), [commands]);
  const activeMode = MODES.find((m) => m.id === mode) ?? MODES[0]!;
  const explicit = text.trim().startsWith("/");

  const submit = async () => {
    const body = text.trim();
    if (!body || busy) return;
    setBusy(true);
    setError(null);
    const content = explicit ? body : `${activeMode.command} ${body}`;
    try {
      const out = await dashboardApi.quickstart({ content, project_id: projectId || undefined, selected_asset_ids: selected });
      window.dispatchEvent(new Event(RECENTS_CHANGED));
      router.push(`/app/projects/${out.project_id}/chat/${out.conversation_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start");
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-3xl">
      <div className="hero-composer rounded-2xl border border-border bg-surface shadow-card transition">
        <textarea
          ref={ref}
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void submit();
            }
          }}
          placeholder={explicit ? "Command detected — the slash command takes precedence" : `${activeMode.hint}… e.g. "Adapt the approved poster to 4:5 and 9:16 with the logo top-left"`}
          className="w-full resize-none bg-transparent px-5 pt-4 text-[15px] leading-relaxed outline-none placeholder:text-faint"
        />
        <div className="flex flex-wrap items-center gap-2 px-3 pb-3">
          <div className="flex flex-wrap gap-1">
            {MODES.map((m) => {
              const enabled = available.size === 0 || available.has(m.command);
              return (
                <button
                  key={m.id}
                  onClick={() => setMode(m.id)}
                  disabled={!enabled}
                  title={enabled ? m.hint : `${m.command} is not active — ask an admin`}
                  className={`rounded-full px-3 py-1 text-xs font-medium transition ${mode === m.id ? "bg-accent text-accent-contrast" : "bg-surface-2 text-muted hover:text-text"} disabled:opacity-40`}
                >
                  {m.label}
                </button>
              );
            })}
          </div>
          <div className="ml-auto flex items-center gap-2">
            <select className="max-w-[180px] rounded-md border border-border bg-surface px-2 py-1 text-xs" value={projectId} onChange={(e) => { setProjectId(e.target.value); setSelected([]); setAssets([]); }} aria-label="Project">
              <option value="">Scratchpad (auto)</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.workspace_name} / {p.name}</option>)}
            </select>
            <button className={`rounded-md p-1.5 ${selected.length ? "text-accent" : "text-muted"} hover:bg-surface-2`} title="Attach assets" onClick={() => setShowAssets((s) => !s)} disabled={!projectId}><Paperclip size={16} /></button>
            <button onClick={() => void submit()} disabled={!text.trim() || busy} className="flex h-9 w-9 items-center justify-center rounded-full bg-accent text-accent-contrast hover:opacity-90 disabled:opacity-40" aria-label="Start">{busy ? <Sparkles size={16} className="animate-pulse" /> : <ArrowUp size={16} />}</button>
          </div>
        </div>
        {showAssets && projectId ? (
          <div className="flex flex-wrap gap-1 border-t border-border px-4 py-2">
            {assets.length === 0 ? <span className="text-xs text-faint">No assets in this project yet — upload from Library.</span> : null}
            {assets.map((a) => (
              <label key={a.id} className="flex items-center gap-1 rounded border border-border px-2 py-0.5 text-[11px]">
                <input type="checkbox" checked={selected.includes(a.id)} onChange={(e) => setSelected(e.target.checked ? [...selected, a.id] : selected.filter((x) => x !== a.id))} /> {a.name}
              </label>
            ))}
          </div>
        ) : null}
      </div>
      {error ? <p className="mt-2 text-center text-xs text-danger">{error}</p> : null}
      <p className="mt-2 text-center text-[11px] text-faint">Enter to start · Shift+Enter for a new line · type “/” to address a specific agent</p>
    </div>
  );
}
