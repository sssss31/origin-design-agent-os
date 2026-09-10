"use client";

import { useCallback, useEffect, useState } from "react";
import { AdminShell, useAsyncAction } from "@/components/admin/AdminShell";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardTitle, EmptyState, ErrorText } from "@/components/ui/Card";
import { Field, Input, Textarea } from "@/components/ui/Input";
import { JsonField, Select } from "@/components/ui/JsonField";
import { toolsApi } from "@/lib/api/admin";
import type { ToolOut } from "@/types/admin";

export default function ToolsPage() {
  const run = useAsyncAction();
  const [tools, setTools] = useState<ToolOut[] | null>(null);
  const [slug, setSlug] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [executor, setExecutor] = useState("http_api");
  const [input, setInput] = useState<Record<string, unknown>>({ type: "object", properties: {} });
  const [config, setConfig] = useState<Record<string, unknown>>({ url: "", method: "POST" });
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => toolsApi.list().then(setTools).catch(() => setTools([])), []);
  useEffect(() => { void load(); }, [load]);
  return (
    <AdminShell title="Tools">
      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <section className="space-y-3">
          {tools === null ? <p className="text-sm text-muted">Loading…</p> : null}
          {tools?.length === 0 ? <EmptyState title="No tools" body="Built-in image/file/SVG/PDF tools are registered in Phase 6. HTTP and MCP tools can be added now." /> : null}
          {tools?.map((t) => <ToolCard key={t.id} tool={t} onChange={(nt) => setTools((list) => (list ?? []).map((x) => (x.id === nt.id ? nt : x)))} />)}
        </section>
        <aside>
          <Card>
            <CardTitle>Create tool</CardTitle>
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void run(async () => { await toolsApi.create({ slug, display_name: displayName, description, executor_type: executor, input_schema: input, config }); setSlug(""); setDisplayName(""); await load(); }, setError); }}>
              <Field label="Slug" hint="e.g. image.inspect"><Input required value={slug} onChange={(e) => setSlug(e.target.value)} /></Field>
              <Field label="Display name"><Input required value={displayName} onChange={(e) => setDisplayName(e.target.value)} /></Field>
              <Field label="Description"><Textarea value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
              <Select label="Executor" value={executor} onChange={setExecutor} options={[{ value: "http_api", label: "HTTP API" }, { value: "mcp", label: "MCP server" }, { value: "sandbox", label: "Sandbox" }, { value: "internal_function", label: "Internal function" }]} />
              <JsonField label="Input schema" value={input} onChange={setInput} rows={5} />
              <JsonField label="Executor config" value={config} onChange={setConfig} rows={4} />
              <ErrorText>{error}</ErrorText>
              <Button type="submit" disabled={!slug.trim() || !displayName.trim()}>Create</Button>
            </form>
          </Card>
        </aside>
      </div>
    </AdminShell>
  );
}

function ToolCard({ tool: t, onChange }: { tool: ToolOut; onChange: (t: ToolOut) => void }) {
  const run = useAsyncAction();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState<Record<string, unknown>>(t.active_version?.input_schema ?? {});
  const [config, setConfig] = useState<Record<string, unknown>>(t.active_version?.config ?? {});
  const [timeout, setTimeoutS] = useState(String(t.active_version?.timeout_seconds ?? 60));
  const [secret, setSecret] = useState("");
  const [role, setRole] = useState("member");
  const [error, setError] = useState<string | null>(null);
  return (
    <Card className="space-y-2">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold">{t.display_name} <span className="font-mono text-xs text-muted">{t.slug}</span></p>
          <p className="text-xs text-muted">{t.description || "—"}</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge>{t.executor_type}</Badge>
          {t.active_version ? <Badge tone="accent">v{t.active_version.version}</Badge> : null}
          {t.is_builtin ? <Badge>built-in</Badge> : null}
          <Badge tone={t.status === "active" ? "success" : "neutral"}>{t.status}</Badge>
          <Button variant="secondary" onClick={() => void run(async () => onChange(await toolsApi.update(t.id, { status: t.status === "active" ? "disabled" : "active" })), setError)}>{t.status === "active" ? "Disable" : "Enable"}</Button>
          <Button variant="ghost" onClick={() => setOpen(!open)}>{open ? "Close" : "Edit"}</Button>
        </div>
      </div>
      {open ? (
        <div className="grid gap-3 border-t border-border pt-3 md:grid-cols-2">
          <div className="space-y-2">
            <JsonField label="Input schema (new version on save)" value={input} onChange={setInput} rows={6} />
            <JsonField label="Executor config" value={config} onChange={setConfig} rows={4} />
            <Field label="Timeout (s)"><Input type="number" value={timeout} onChange={(e) => setTimeoutS(e.target.value)} /></Field>
            <Button onClick={() => void run(async () => onChange(await toolsApi.update(t.id, { input_schema: input, config, timeout_seconds: Number(timeout) })), setError)}>Save as new version</Button>
          </div>
          <div className="space-y-3">
            <div className="space-y-2 rounded-md border border-border p-3">
              <p className="text-xs font-medium">Credential {t.active_version?.has_secret ? <Badge tone="success">stored</Badge> : <Badge>none</Badge>}</p>
              <Input type="password" autoComplete="off" placeholder="Write-only secret for http/mcp tools" value={secret} onChange={(e) => setSecret(e.target.value)} />
              <Button variant="secondary" disabled={!secret} onClick={() => void run(async () => { onChange(await toolsApi.setSecret(t.id, secret)); setSecret(""); }, setError)}>Save secret</Button>
            </div>
            <div className="space-y-2 rounded-md border border-border p-3">
              <p className="text-xs font-medium">Who may trigger runs using this tool</p>
              <ul className="text-xs">
                {t.permissions.map((p) => (
                  <li key={p.id} className="flex justify-between py-1"><span>{p.subject_type}: {p.subject_key} {p.allowed ? "" : "(denied)"}</span><button className="text-accent" onClick={() => void run(async () => onChange(await toolsApi.deletePermission(t.id, p.id)), setError)}>remove</button></li>
                ))}
                {t.permissions.length === 0 ? <li className="text-muted">No restrictions (any member of the organization).</li> : null}
              </ul>
              <div className="flex gap-2">
                <Select value={role} onChange={setRole} options={[{ value: "admin", label: "role: admin" }, { value: "member", label: "role: member" }, { value: "viewer", label: "role: viewer" }]} />
                <Button variant="secondary" onClick={() => void run(async () => onChange(await toolsApi.setPermission(t.id, { subject_type: "role", subject_key: role, allowed: true })), setError)}>Allow</Button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
      <ErrorText>{error}</ErrorText>
    </Card>
  );
}
