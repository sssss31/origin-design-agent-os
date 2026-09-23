"use client";

import { Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { WorkspaceShell } from "@/components/workspace/WorkspaceShell";
import { Badge, Card, EmptyState } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/JsonField";
import { commandsApi } from "@/lib/api/admin";
import { workApi } from "@/lib/api/work";
import type { CommandOut } from "@/types/admin";
import type { WorkItem } from "@/types/work";

/** Workspace V0 §20–§22: My Work — history, search, filters, reopen. */
export default function MyWorkPage() {
  const [search, setSearch] = useState("");
  const [agent, setAgent] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [agents, setAgents] = useState<CommandOut[]>([]);
  const [items, setItems] = useState<WorkItem[] | null>(null);
  useEffect(() => {
    commandsApi.list().then(setAgents).catch(() => setAgents([]));
  }, []);
  useEffect(() => {
    const t = setTimeout(() => {
      workApi.list({ search: search || undefined, agent_id: agent || undefined, date_from: from ? new Date(from).toISOString() : undefined, date_to: to ? new Date(`${to}T23:59:59`).toISOString() : undefined }).then(setItems).catch(() => setItems([]));
    }, 200);
    return () => clearTimeout(t);
  }, [search, agent, from, to]);
  return (
    <WorkspaceShell>
      <div className="flex-1 overflow-y-auto">
        <div className="px-8 pt-7 pb-4">
          <h1 className="text-xl font-semibold tracking-tight">My Work</h1>
          <p className="mt-1 text-sm text-muted">Everything you worked on: conversations, agents used, files and outputs.</p>
        </div>
        <div className="flex flex-wrap items-end gap-2 px-8 pb-4">
          <div className="relative w-72"><Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint" /><Input className="pl-8" placeholder="Search title, messages, files, agent…" value={search} onChange={(e) => setSearch(e.target.value)} /></div>
          <div className="w-52"><Select value={agent} onChange={setAgent} options={[{ value: "", label: "All agents" }, ...agents.map((a) => ({ value: a.agent_id, label: `${a.name} ${a.command}` }))]} /></div>
          <Input type="date" className="w-40" value={from} onChange={(e) => setFrom(e.target.value)} aria-label="From" />
          <Input type="date" className="w-40" value={to} onChange={(e) => setTo(e.target.value)} aria-label="To" />
          <span className="ml-auto text-xs text-faint">{items?.length ?? 0} items</span>
        </div>
        <div className="grid gap-3 px-8 pb-10 sm:grid-cols-2 xl:grid-cols-3">
          {items === null ? <p className="text-sm text-muted">Loading…</p> : items.length === 0 ? <div className="sm:col-span-2 xl:col-span-3"><EmptyState title="Nothing here yet" body="Start a chat with /agent and it will show up here with its files and outputs." /></div> : null}
          {items?.map((w) => (
            <Link key={w.conversation_id} href={`/chat/${w.conversation_id}`}>
              <Card className="h-full hover:border-accent">
                <p className="truncate text-sm font-semibold">{w.title}</p>
                <p className="mt-0.5 text-xs text-muted">Agent: {w.primary_agent ?? "—"}{w.agents_used.length > 1 ? ` (+${w.agents_used.length - 1})` : ""}</p>
                <p className="text-[11px] text-faint">{new Date(w.last_message_at ?? w.created_at).toLocaleDateString(undefined, { month: "long", day: "numeric" })} · {w.project_name}</p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {w.agents_used.map((a) => <Badge key={a.id} tone="accent">{a.command}</Badge>)}
                </div>
                <p className="mt-2 text-xs text-muted">{w.messages} messages · {w.files} files · {w.outputs} outputs</p>
              </Card>
            </Link>
          ))}
        </div>
      </div>
    </WorkspaceShell>
  );
}
