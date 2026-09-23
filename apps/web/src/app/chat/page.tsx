"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { WorkspaceShell } from "@/components/workspace/WorkspaceShell";
import { commandsApi } from "@/lib/api/admin";
import { conversationsApi } from "@/lib/api/chat";
import { api } from "@/lib/api/client";
import { RECENTS_CHANGED } from "@/components/shell/AppShell";
import type { CommandOut } from "@/types/admin";

/** Workspace V0 §23: New Chat screen — "What do you want to work on? Type / to select an Agent". */
export default function ChatHome() {
  const router = useRouter();
  const [commands, setCommands] = useState<CommandOut[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    commandsApi.list().then(setCommands).catch(() => setCommands([]));
  }, []);
  const start = async (command?: string) => {
    setBusy(true);
    try {
      const projects = (await api<{ projects: { id: string }[] }>("/library?limit=1")).projects;
      const projectId = projects[0]?.id;
      const conv = projectId
        ? await conversationsApi.create(projectId)
        : await api<{ conversation_id: string }>("/quickstart", { method: "POST", body: { content: "/auto", title: "New chat" } }).then((o) => ({ id: o.conversation_id }));
      if (command) await conversationsApi.setActiveAgent(conv.id, { command });
      window.dispatchEvent(new Event(RECENTS_CHANGED));
      router.push(`/chat/${conv.id}`);
    } finally {
      setBusy(false);
    }
  };
  return (
    <WorkspaceShell>
      <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">What do you want to work on?</h1>
        <p className="mt-2 text-sm text-muted">Type <span className="font-mono">/</span> to select an agent. Follow-ups stay with that agent until you switch.</p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          {commands.length === 0 ? <p className="text-xs text-faint">No agents connected yet — an admin can add them under Admin → Agents.</p> : null}
          {commands.map((c) => (
            <button key={c.agent_id} disabled={busy} onClick={() => void start(c.command)} className="rounded-full border border-border bg-surface px-3 py-1.5 text-sm hover:border-accent" title={c.description}>
              <span className="font-mono text-accent">{c.command}</span> <span className="text-muted">{c.name}</span>
            </button>
          ))}
        </div>
        <button disabled={busy} onClick={() => void start()} className="mt-8 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-contrast">{busy ? "Creating…" : "+ New Chat"}</button>
      </div>
    </WorkspaceShell>
  );
}
