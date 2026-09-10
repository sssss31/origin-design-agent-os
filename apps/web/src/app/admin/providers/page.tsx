"use client";

import { useCallback, useEffect, useState } from "react";
import { AdminShell, useAsyncAction } from "@/components/admin/AdminShell";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardTitle, EmptyState, ErrorText } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/JsonField";
import { providersApi } from "@/lib/api/admin";
import type { ProviderOut, ProviderTestOut } from "@/types/admin";

export default function ProvidersPage() {
  const run = useAsyncAction();
  const [providers, setProviders] = useState<ProviderOut[] | null>(null);
  const [name, setName] = useState("");
  const [type, setType] = useState("openai");
  const [baseUrl, setBaseUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => providersApi.list().then(setProviders).catch(() => setProviders([])), []);
  useEffect(() => { void load(); }, [load]);
  return (
    <AdminShell title="AI providers">
      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <section className="space-y-3">
          {providers === null ? <p className="text-sm text-muted">Loading…</p> : null}
          {providers?.length === 0 ? <EmptyState title="No providers" body="Add OpenAI (or the echo provider for offline testing) to let agents run." /> : null}
          {providers?.map((p) => <ProviderCard key={p.id} provider={p} onChange={(np) => setProviders((list) => (list ?? []).map((x) => (x.id === np.id ? np : x)))} />)}
        </section>
        <aside>
          <Card>
            <CardTitle>Add provider</CardTitle>
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void run(async () => { await providersApi.create({ name, type, base_url: baseUrl || undefined }); setName(""); setBaseUrl(""); await load(); }, setError); }}>
              <Field label="Name"><Input required value={name} onChange={(e) => setName(e.target.value)} placeholder="OpenAI Production" /></Field>
              <Select label="Type" value={type} onChange={setType} options={[{ value: "openai", label: "OpenAI" }, { value: "echo", label: "Echo (offline test runner)" }]} />
              <Field label="Base URL" hint="Leave empty for the provider default."><Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} /></Field>
              <ErrorText>{error}</ErrorText>
              <Button type="submit" disabled={!name.trim()}>Add</Button>
            </form>
          </Card>
        </aside>
      </div>
    </AdminShell>
  );
}

function ProviderCard({ provider: p, onChange }: { provider: ProviderOut; onChange: (p: ProviderOut) => void }) {
  const run = useAsyncAction();
  const [key, setKey] = useState("");
  const [test, setTest] = useState<ProviderTestOut | null>(null);
  const [models, setModels] = useState(p.models.map((m) => m.model).join("\n"));
  const [defaultModel, setDefaultModel] = useState(p.default_model ?? "");
  const [error, setError] = useState<string | null>(null);
  const health = { ok: "success", error: "danger", unknown: "neutral" } as const;
  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold">{p.name} <span className="font-mono text-xs text-muted">{p.type}</span></p>
          <p className="text-xs text-muted">{p.base_url}</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={health[p.health_status]}>{p.health_status}</Badge>
          <Badge tone={p.enabled ? "success" : "neutral"}>{p.enabled ? "enabled" : "disabled"}</Badge>
          <Button variant="secondary" onClick={() => void run(async () => onChange(await providersApi.update(p.id, { enabled: !p.enabled })), setError)}>{p.enabled ? "Disable" : "Enable"}</Button>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-2 rounded-md border border-border p-3">
          <p className="text-xs font-medium">Credential {p.has_secret ? <Badge tone="success">stored {p.secret_fingerprint}</Badge> : <Badge tone="warning">missing</Badge>}</p>
          <Input type="password" autoComplete="off" placeholder={p.has_secret ? "Rotate: paste a new API key" : "Paste API key (write-only)"} value={key} onChange={(e) => setKey(e.target.value)} />
          <div className="flex gap-2">
            <Button disabled={key.length < 8} onClick={() => void run(async () => { onChange(await providersApi.setSecret(p.id, key)); setKey(""); }, setError)}>{p.has_secret ? "Rotate key" : "Save key"}</Button>
            <Button variant="secondary" onClick={() => void run(async () => { const t = await providersApi.test(p.id); setTest(t); onChange({ ...p, health_status: t.ok ? "ok" : "error", health_message: t.message, last_tested_at: t.tested_at }); }, setError)}>Test connection</Button>
          </div>
          {test ? <p className={`text-xs ${test.ok ? "text-success" : "text-danger"}`}>{test.message} · {test.latency_ms} ms{test.available_models.length ? ` · ${test.available_models.length} models visible` : ""}</p> : p.health_message ? <p className="text-xs text-muted">{p.health_message}{p.last_tested_at ? ` · ${new Date(p.last_tested_at).toLocaleString()}` : ""}</p> : null}
          {test?.available_models.length ? <Button variant="ghost" onClick={() => setModels(test.available_models.join("\n"))}>Use visible models as allowlist</Button> : null}
        </div>
        <div className="space-y-2 rounded-md border border-border p-3">
          <p className="text-xs font-medium">Model allowlist (one per line)</p>
          <textarea className="min-h-20 w-full rounded-md border border-border bg-surface px-2 py-1 font-mono text-xs" value={models} onChange={(e) => setModels(e.target.value)} aria-label="Allowed models" />
          <Field label="Default model"><Input value={defaultModel} onChange={(e) => setDefaultModel(e.target.value)} /></Field>
          <Button variant="secondary" onClick={() => void run(async () => onChange(await providersApi.setModels(p.id, models.split("\n").map((m) => m.trim()).filter(Boolean).map((model) => ({ model })), defaultModel || null)), setError)}>Save allowlist</Button>
        </div>
      </div>
      <ErrorText>{error}</ErrorText>
    </Card>
  );
}
