"use client";

import { Plug, Plus, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { AdminShell, useAsyncAction } from "@/components/admin/AdminShell";
import { OpenAIConnectWizard } from "@/components/admin/OpenAIConnectWizard";
import { Button } from "@/components/ui/Button";
import { Badge, Card, EmptyState, ErrorText } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { providersApi } from "@/lib/api/admin";
import { api } from "@/lib/api/client";
import type { ProviderConnectionOut, ProviderOut } from "@/types/admin";
import type { IntegrationsOverview, ProviderCard as ProviderCardData } from "@/types/integrations";

function IntegrationsPage() {
  const params = useSearchParams();
  const [data, setData] = useState<IntegrationsOverview | null>(null);
  const [wizard, setWizard] = useState<{ open: boolean; existing: ProviderOut | null }>({ open: params.get("add") === "1", existing: null });
  const load = useCallback(() => api<IntegrationsOverview>("/admin/integrations/overview").then(setData).catch(() => setData({ provider_types: [], providers: [], custom: [] })), []);
  useEffect(() => {
    void load();
  }, [load]);
  const openai = data?.providers.filter((c) => c.provider.type === "openai") ?? [];
  const others = data?.providers.filter((c) => c.provider.type !== "openai") ?? [];
  return (
    <AdminShell title="API Integrations">
      <div className="space-y-6">
        <section id="openai" className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold">Model providers</h2>
              <p className="text-xs text-muted">The API key authenticates the provider; agents choose a provider and an allowed model. Keys are encrypted server-side and never returned.</p>
            </div>
            <Button onClick={() => setWizard({ open: true, existing: null })}><Plus size={14} /> Connect OpenAI</Button>
          </div>
          {wizard.open ? <OpenAIConnectWizard existing={wizard.existing} onDone={() => void load()} onCancel={() => { setWizard({ open: false, existing: null }); void load(); }} /> : null}
          {data === null ? <p className="text-sm text-muted">Loading…</p> : null}
          {data && openai.length === 0 && !wizard.open ? <EmptyState title="OpenAI is not connected" body="Connect OpenAI to let agents run on GPT models. Use the Echo provider for offline testing." /> : null}
          <div className="grid gap-4 xl:grid-cols-2">
            {openai.map((c) => <ProviderCard key={c.provider.id} card={c} onChanged={() => void load()} onReconfigure={() => setWizard({ open: true, existing: c.provider })} />)}
            {others.map((c) => <ProviderCard key={c.provider.id} card={c} onChanged={() => void load()} onReconfigure={() => undefined} />)}
          </div>
        </section>

        <section id="custom" className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold">Custom REST APIs</h2>
              <p className="text-xs text-muted">Connect any HTTP endpoint (or import a cURL) as a tool agents can call. Credentials are extracted into encrypted secret references.</p>
            </div>
            <Link href="/admin/integrations/custom/new"><Button variant="secondary"><Plug size={14} /> Add Custom API</Button></Link>
          </div>
          {data && data.custom.length === 0 ? <EmptyState title="No custom APIs yet" body="Add an internal SVG engine, an image processor, a smart-crop service or any REST API." /> : null}
          <div className="grid gap-4 xl:grid-cols-2">
            {data?.custom.map((c) => (
              <Link key={c.id} href={`/admin/integrations/custom/${c.id}`}>
                <Card className="hover:border-accent">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-semibold uppercase tracking-wide">{c.name}</p>
                    <Badge tone={c.health_status === "ok" ? "success" : c.health_status === "error" ? "danger" : "neutral"}>{c.health_status === "ok" ? "● Connected" : c.health_status === "error" ? "● Failed" : "untested"}</Badge>
                  </div>
                  <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                    <dt className="text-muted">Method</dt><dd className="font-mono">{c.method}</dd>
                    <dt className="text-muted">Endpoint</dt><dd className="truncate font-mono">{c.endpoint.replace(/^https?:\/\//, "")}</dd>
                    <dt className="text-muted">Authentication</dt><dd>{c.secrets.length ? "••••••••" : "none"}</dd>
                    <dt className="text-muted">Used by</dt><dd>{c.used_by.join(", ") || "—"}</dd>
                    <dt className="text-muted">Average latency</dt><dd>{c.avg_latency_ms != null ? `${(c.avg_latency_ms / 1000).toFixed(1)} sec` : "—"}</dd>
                  </dl>
                </Card>
              </Link>
            ))}
          </div>
        </section>
      </div>
    </AdminShell>
  );
}

function ProviderCard({ card, onChanged, onReconfigure }: { card: ProviderCardData; onChanged: () => void; onReconfigure: () => void }) {
  const p = card.provider;
  const run = useAsyncAction();
  const [test, setTest] = useState<ProviderConnectionOut | null>(null);
  const [key, setKey] = useState("");
  const [rotating, setRotating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const connected = p.health_status === "ok";
  const statusLabel = !p.configured ? "Not configured" : connected ? "● Connected" : p.health_status === "error" ? "● Connection Failed" : "○ Untested";
  const tone = !p.configured ? "warning" : connected ? "success" : p.health_status === "error" ? "danger" : "neutral";
  return (
    <Card className="space-y-3">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide">{p.type === "openai" ? "OpenAI" : p.name}</p>
          <p className="text-xs text-muted">{p.name} · {p.base_url}</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={tone}>{statusLabel}</Badge>
          {p.is_default ? <Badge tone="accent">default</Badge> : null}
          {!p.enabled ? <Badge tone="neutral">disabled</Badge> : null}
        </div>
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3">
        <dt className="text-muted">API key</dt><dd className="font-mono">{p.key_preview ?? (p.type === "echo" ? "not required" : "—")}</dd>
        <dt className="text-muted">Environment</dt><dd className="capitalize">{p.environment}</dd>
        <dt className="text-muted">Models</dt><dd>{p.models.filter((m) => m.enabled).length} allowed{p.default_model ? ` · default ${p.default_model}` : ""}</dd>
        <dt className="text-muted">Usage this month</dt><dd>{card.estimated_cost_month_usd != null ? `$${card.estimated_cost_month_usd.toFixed(2)}` : `${card.tokens_month.toLocaleString()} tokens`}</dd>
        <dt className="text-muted">Requests</dt><dd>{card.requests_month.toLocaleString()}{card.avg_latency_ms != null ? ` · ${card.avg_latency_ms} ms avg` : ""}</dd>
        <dt className="text-muted">Used by</dt><dd>{card.used_by.join(", ") || "no active agents"}</dd>
      </dl>
      {test ? <p className={`text-xs ${test.success ? "text-success" : "text-danger"}`}>{test.success ? "🟢 Connected" : "🔴 Connection Failed"} — {test.message} ({test.latency_ms} ms)</p> : p.health_message ? <p className="text-xs text-muted">{p.health_message}{p.last_tested_at ? ` · ${new Date(p.last_tested_at).toLocaleString()}` : ""}</p> : null}
      {rotating ? (
        <div className="flex gap-2">
          <Input type="password" autoComplete="off" placeholder="Paste the new API key" value={key} onChange={(e) => setKey(e.target.value)} />
          <Button disabled={key.length < 20 || busy} onClick={() => { setBusy(true); void run(async () => { await providersApi.setSecret(p.id, key); setKey(""); setRotating(false); onChanged(); }, setError).finally(() => setBusy(false)); }}>Update key</Button>
          <Button variant="ghost" onClick={() => setRotating(false)}>Cancel</Button>
        </div>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" disabled={busy || !p.configured} onClick={() => { setBusy(true); void run(async () => { setTest(await providersApi.connectionTest(p.id)); onChanged(); }, setError).finally(() => setBusy(false)); }}><RefreshCw size={13} className={busy ? "animate-spin" : ""} /> Test Connection</Button>
        {p.type !== "echo" ? <Button variant="secondary" onClick={() => setRotating(true)}>Update Key</Button> : null}
        {p.type === "openai" ? <Button variant="secondary" onClick={onReconfigure}>Manage Models</Button> : null}
        {!p.is_default && p.configured ? <Button variant="secondary" onClick={() => void run(async () => { await providersApi.setDefault(p.id); onChanged(); }, setError)}>Set as default</Button> : null}
        {p.configured ? <Button variant="secondary" onClick={() => { if (window.confirm(`Switch every agent to ${p.name}?`)) void run(async () => { const r = await providersApi.adopt(p.id); window.alert(`Switched ${r.switched} agents (${r.skipped} already on it, ${r.failed} failed).`); onChanged(); }, setError); }}>Use for all agents</Button> : null}
        <Button variant="secondary" onClick={() => void run(async () => { await providersApi.update(p.id, { enabled: !p.enabled }); onChanged(); }, setError)}>{p.enabled ? "Disable" : "Enable"}</Button>
        <Button variant="ghost" onClick={() => { if (window.confirm(`Delete ${p.name}? Agents using it must be reassigned first.`)) void run(async () => { await providersApi.remove(p.id); onChanged(); }, setError); }}>Delete</Button>
      </div>
      <ErrorText>{error}</ErrorText>
    </Card>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-muted">Loading…</div>}>
      <IntegrationsPage />
    </Suspense>
  );
}
