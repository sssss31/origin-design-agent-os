"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AdminShell, useAsyncAction } from "@/components/admin/AdminShell";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardTitle, EmptyState, ErrorText } from "@/components/ui/Card";
import { Field, Input, Textarea } from "@/components/ui/Input";
import { agentsApi, providersApi } from "@/lib/api/admin";
import type { AgentSummaryOut, ProviderCurlPreview } from "@/types/admin";

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
  const [mode, setMode] = useState<"form" | "curl">("form");
  const [curl, setCurl] = useState("");
  const [preview, setPreview] = useState<ProviderCurlPreview | null>(null);
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
          {agents?.length === 0 ? (
            <Card>
              <EmptyState title="No agents yet" body="Create the eight workspace commands (/master, /resize, /editable, /qc, /copy, /asset, /export, /agent8) and then add each agent's endpoint and key." />
              <div className="mt-3 flex justify-center">
                <Button variant="secondary" onClick={() => void run(() => agentsApi.seedRegistry("openai_responses").then(() => agentsApi.list().then(setAgents)), setError)}>Create the 8 agent entries</Button>
              </div>
            </Card>
          ) : null}
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
                    {a.connection && a.connection.connection_type !== "origin" ? (
                      <Badge tone={a.connection.connection_status === "ok" ? "success" : a.connection.connection_status === "error" ? "danger" : "neutral"}>
                        {a.connection.connection_status === "ok" ? "connected" : a.connection.connection_status === "error" ? "connection failed" : a.connection.configured ? "key configured" : "no key"}
                      </Badge>
                    ) : null}
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
            <div className="mb-3 flex w-fit gap-1 rounded-lg border border-border bg-surface p-0.5">
              {(["curl", "form"] as const).map((m) => (
                <button key={m} type="button" onClick={() => setMode(m)} className={`rounded-md px-3 py-1 text-xs font-medium ${mode === m ? "bg-accent-soft text-accent" : "text-muted hover:text-text"}`}>{m === "curl" ? "From the agent's cURL" : "Manually"}</button>
              ))}
            </div>
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                void run(async () => {
                  if (mode === "curl") {
                    const out = await agentsApi.importCurl({ curl, name, command, description, instructions: instructions || undefined });
                    router.push(`/admin/agents/${out.agent.id}`);
                    return;
                  }
                  const created = await agentsApi.create({ name, command, description, version: { instructions } });
                  router.push(`/admin/agents/${created.id}`);
                }, setError);
              }}
            >
              <Field label="Name"><Input required value={name} onChange={(e) => setName(e.target.value)} /></Field>
              <Field label="Slash command" hint="lowercase, e.g. /resize"><Input required value={command} onChange={(e) => setCommand(e.target.value)} placeholder="/resize" /></Field>
              <Field label="Routing description"><Input value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
              {mode === "curl" ? (
                <>
                  <Field label="Agent cURL (OpenAI Responses or Chat Completions)" hint="The Bearer token becomes the provider key (encrypted), the model is allowlisted, and instructions/settings are copied into the agent. The command is not stored.">
                    <Textarea rows={8} className="font-mono text-xs" value={curl} onChange={(e) => { setCurl(e.target.value); setPreview(null); }} placeholder={'curl https://api.openai.com/v1/responses -H "Authorization: Bearer sk-…" -d \'{"model":"gpt-5","instructions":"…"}\''} />
                  </Field>
                  {preview ? (
                    <div className="rounded-md border border-border p-2 text-xs">
                      <p><b>{preview.model ?? "no model"}</b> · {preview.endpoint_kind} · key {preview.key_preview ?? (preview.key_placeholder ? "placeholder ⚠" : "missing")} · instructions {preview.instructions ? `${preview.instructions.length} chars` : "none (add below)"}</p>
                      {preview.warnings.map((w) => <p key={w} className="text-warning">⚠ {w}</p>)}
                    </div>
                  ) : null}
                  <Button type="button" variant="secondary" disabled={curl.trim().length < 8} onClick={() => void run(async () => setPreview(await providersApi.parseCurl(curl)), setError)}>Preview</Button>
                  <Field label={preview?.instructions ? "Instructions (override, optional)" : "Instructions"} hint="Used when the cURL has none (e.g. it references a stored prompt id)."><Textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} /></Field>
                </>
              ) : (
                <Field label="Initial instructions"><Textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} /></Field>
              )}
              <ErrorText>{error}</ErrorText>
              <Button type="submit" disabled={!name.trim() || !command.trim() || (mode === "curl" && curl.trim().length < 8)}>{mode === "curl" ? "Import & create" : "Create draft"}</Button>
            </form>
          </Card>
        </aside>
      </div>
    </AdminShell>
  );
}
