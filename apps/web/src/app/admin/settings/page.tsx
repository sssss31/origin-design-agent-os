"use client";

import { useEffect, useState } from "react";
import { AdminShell, useAsyncAction } from "@/components/admin/AdminShell";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardTitle, ErrorText } from "@/components/ui/Card";
import { Field, Input, Textarea } from "@/components/ui/Input";
import { Select } from "@/components/ui/JsonField";
import { api } from "@/lib/api/client";

interface SystemSettings { organization_id: string; name: string; global_rules: string | null; display_currency: string; fx_usd_rate: number; quota_runs_per_day: number; default_max_revisions: number; outbound: { allow_http: boolean; allowed_hosts: string[]; max_response_bytes: number; default_timeout_seconds: number; provider_retry_attempts: number }; environment: string }

export default function SettingsPage() {
  const run = useAsyncAction();
  const [s, setS] = useState<SystemSettings | null>(null);
  const [form, setForm] = useState({ name: "", global_rules: "", display_currency: "INR", fx_usd_rate: "83", quota_runs_per_day: "500", default_max_revisions: "1" });
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => {
    api<SystemSettings>("/admin/settings").then((d) => { setS(d); setForm({ name: d.name, global_rules: d.global_rules ?? "", display_currency: d.display_currency, fx_usd_rate: String(d.fx_usd_rate), quota_runs_per_day: String(d.quota_runs_per_day), default_max_revisions: String(d.default_max_revisions) }); }).catch(() => setS(null));
  }, []);
  return (
    <AdminShell title="System Settings">
      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <Card className="space-y-3">
          <CardTitle>Organization</CardTitle>
          <Field label="Name"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label="Global rules" hint="Injected into every agent prompt after the platform rules (composition order: platform → organization → agent → skills → workspace → project)."><Textarea rows={8} value={form.global_rules} onChange={(e) => setForm({ ...form, global_rules: e.target.value })} /></Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Select label="Display currency" value={form.display_currency} onChange={(v) => setForm({ ...form, display_currency: v })} options={["INR", "USD", "EUR", "GBP"].map((c) => ({ value: c, label: c }))} />
            <Field label="FX rate (1 USD = ?)" hint="Costs are stored in USD and converted for display."><Input type="number" step="0.01" value={form.fx_usd_rate} onChange={(e) => setForm({ ...form, fx_usd_rate: e.target.value })} /></Field>
            <Field label="Run quota per day (0 = unlimited)"><Input type="number" value={form.quota_runs_per_day} onChange={(e) => setForm({ ...form, quota_runs_per_day: e.target.value })} /></Field>
            <Field label="Default QC revisions"><Input type="number" min={0} max={5} value={form.default_max_revisions} onChange={(e) => setForm({ ...form, default_max_revisions: e.target.value })} /></Field>
          </div>
          <Button onClick={() => void run(async () => { setNotice(null); const d = await api<SystemSettings>("/admin/settings", { method: "PUT", body: { name: form.name, global_rules: form.global_rules, display_currency: form.display_currency, fx_usd_rate: Number(form.fx_usd_rate), quota_runs_per_day: Number(form.quota_runs_per_day), default_max_revisions: Number(form.default_max_revisions) } }); setS(d); setNotice("Saved"); }, setError)}>Save</Button>
          {notice ? <p className="text-xs text-success">{notice}</p> : null}
          <ErrorText>{error}</ErrorText>
        </Card>
        <Card className="space-y-2">
          <CardTitle>Deployment (read-only)</CardTitle>
          {s ? (
            <dl className="grid grid-cols-[150px_1fr] gap-y-1 text-xs">
              <dt className="text-muted">Environment</dt><dd><Badge tone={s.environment === "production" ? "success" : "neutral"}>{s.environment}</Badge></dd>
              <dt className="text-muted">Outbound http</dt><dd>{s.outbound.allow_http ? "allowed (dev)" : "https only"}</dd>
              <dt className="text-muted">Host allowlist</dt><dd>{s.outbound.allowed_hosts.length ? s.outbound.allowed_hosts.join(", ") : "any public host"}</dd>
              <dt className="text-muted">Max response</dt><dd>{(s.outbound.max_response_bytes / 1024 / 1024).toFixed(1)} MB</dd>
              <dt className="text-muted">Default timeout</dt><dd>{s.outbound.default_timeout_seconds} s</dd>
              <dt className="text-muted">Provider retries</dt><dd>{s.outbound.provider_retry_attempts} attempts (retryable errors only)</dd>
            </dl>
          ) : <p className="text-xs text-muted">Loading…</p>}
          <p className="text-[11px] text-muted">These come from environment variables (OUTBOUND_ALLOW_HTTP, OUTBOUND_ALLOWED_HOSTS, OUTBOUND_MAX_RESPONSE_BYTES, PROVIDER_RETRY_ATTEMPTS) and require a deploy to change.</p>
        </Card>
      </div>
    </AdminShell>
  );
}
