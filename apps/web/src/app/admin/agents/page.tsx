"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AdminShell, useAsyncAction } from "@/components/admin/AdminShell";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardTitle, EmptyState, ErrorText } from "@/components/ui/Card";
import { Field, Input, Textarea } from "@/components/ui/Input";
import { agentsApi } from "@/lib/api/admin";
import type { AgentSummaryOut } from "@/types/admin";

const tone = { active: "success", draft: "warning", disabled: "neutral" } as const;

export default function AgentsPage() {
  const router = useRouter();
  const run = useAsyncAction();
  const [agents, setAgents] = useState<AgentSummaryOut[] | null>(null);
  const [filter, setFilter] = useState<"all" | "active" | "draft" | "disabled">("all");
  const [search, setSearch] = useState("");
  const [name, setName] = useState("");
  const [command, setCommand] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    agentsApi.list().then(setAgents).catch(() => setAgents([]));
  }, []);

  const visible = (agents ?? []).filter((a) => (filter === "all" || a.status === filter) && (a.name + a.command).toLowerCase().includes(search.toLowerCase()));

  return (
    <AdminShell title="Agents">
      <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
        <section className="space-y-3">
          <div className="flex gap-2">
            <Input placeholder="Search name or /command" value={search} onChange={(e) => setSearch(e.target.value)} />
            <select className="rounded-md border border-border bg-surface px-2 text-sm" value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)} aria-label="Status filter">
              <option value="all">All</option>
              <option value="active">Active</option>
              <option value="draft">Draft</option>
              <option value="disabled">Disabled</option>
            </select>
          </div>
          {agents === null ? <p className="text-sm text-muted">Loading…</p> : null}
          {agents?.length === 0 ? <EmptyState title="No agents yet" body="Create one on the right. The eight design agents are seeded in Phase 6; you can also add them here." /> : null}
          {visible.map((a) => (
            <Link key={a.id} href={`/admin/agents/${a.id}`} className="block">
              <Card className="hover:border-accent">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold">
                      {a.name} <span className="font-mono text-xs text-accent">{a.command}</span>
                    </p>
                    <p className="truncate text-xs text-muted">{a.description || "—"}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2 text-xs text-muted">
                    {a.model ? <span className="font-mono">{a.model}</span> : null}
                    {a.active_version_number ? <span>v{a.active_version_number}</span> : null}
                    {a.has_draft ? <Badge tone="warning">draft</Badge> : null}
                    {a.is_manager ? <Badge tone="accent">manager</Badge> : null}
                    <Badge tone={tone[a.status]}>{a.status}</Badge>
                  </div>
                </div>
              </Card>
            </Link>
          ))}
        </section>
        <aside>
          <Card>
            <CardTitle>Create agent</CardTitle>
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                void run(async () => {
                  const created = await agentsApi.create({ name, command, description, version: { instructions } });
                  router.push(`/admin/agents/${created.id}`);
                }, setError);
              }}
            >
              <Field label="Name"><Input required value={name} onChange={(e) => setName(e.target.value)} /></Field>
              <Field label="Slash command" hint="lowercase, e.g. /resize"><Input required value={command} onChange={(e) => setCommand(e.target.value)} placeholder="/resize" /></Field>
              <Field label="Routing description"><Input value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
              <Field label="Initial instructions"><Textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} /></Field>
              <ErrorText>{error}</ErrorText>
              <Button type="submit" disabled={!name.trim() || !command.trim()}>Create draft</Button>
            </form>
          </Card>
        </aside>
      </div>
    </AdminShell>
  );
}
