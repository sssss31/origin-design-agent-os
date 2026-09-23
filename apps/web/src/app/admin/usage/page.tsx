"use client";

import { useCallback, useEffect, useState } from "react";
import { AdminShell, useAsyncAction } from "@/components/admin/AdminShell";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardTitle, EmptyState, ErrorText } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/JsonField";
import { api } from "@/lib/api/client";

interface Totals { cost_usd: number; cost_display: number; requests: number; tokens: number; images: number; tool_calls: number; unpriced_calls: number }
interface Summary { currency: string; fx_usd_rate: number; today: Totals; month: Totals; last_30d: Totals }
interface Row { key: string | null; label: string; cost_usd: number; requests: number; input_tokens: number; output_tokens: number; images: number; avg_latency_ms: number }
interface Call { id: string; created_at: string; agent: string | null; command: string | null; provider_type: string; model: string; input_tokens: number; cached_input_tokens: number; output_tokens: number; reasoning_tokens: number; images: number; tool_calls: number; cost_usd: number; priced: boolean; latency_ms: number; status: string; error_code: string | null; run_id: string | null }
interface Pricing { id: string; provider_type: string; model: string; input_per_million: number; cached_input_per_million: number; output_per_million: number; image_per_unit: number; note: string | null; updated_at: string }

const SYMBOL: Record<string, string> = { INR: "₹", USD: "$", EUR: "€", GBP: "£" };
const DIMENSIONS = ["agent", "model", "user", "workspace", "workflow", "provider"] as const;

export default function UsagePage() {
  const run = useAsyncAction();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [by, setBy] = useState<(typeof DIMENSIONS)[number]>("agent");
  const [range, setRange] = useState("month");
  const [rows, setRows] = useState<Row[]>([]);
  const [calls, setCalls] = useState<Call[]>([]);
  const [pricing, setPricing] = useState<Pricing[]>([]);
  const [form, setForm] = useState({ provider_type: "openai", model: "gpt-5*", input_per_million: "", cached_input_per_million: "", output_per_million: "", image_per_unit: "", note: "" });
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    api<Summary>("/admin/usage/summary").then(setSummary).catch(() => setSummary(null));
    api<Row[]>(`/admin/usage/breakdown?by=${by}&range=${range}`).then(setRows).catch(() => setRows([]));
    api<Call[]>("/admin/usage/calls?limit=40").then(setCalls).catch(() => setCalls([]));
    api<Pricing[]>("/admin/usage/pricing").then(setPricing).catch(() => setPricing([]));
  }, [by, range]);
  useEffect(() => { load(); }, [load]);
  const sym = summary ? SYMBOL[summary.currency] ?? summary.currency + " " : "";
  const money = (usd: number) => `${sym}${(usd * (summary?.fx_usd_rate ?? 1)).toFixed(2)}`;
  return (
    <AdminShell title="Usage & Cost">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {summary ? (
          <>
            <Tile label="Today" value={`${sym}${summary.today.cost_display.toFixed(2)}`} sub={`$${summary.today.cost_usd.toFixed(4)}`} />
            <Tile label="This Month" value={`${sym}${summary.month.cost_display.toFixed(2)}`} sub={`$${summary.month.cost_usd.toFixed(4)}`} />
            <Tile label="Requests" value={summary.month.requests.toLocaleString()} sub="this month" />
            <Tile label="Tokens" value={summary.month.tokens.toLocaleString()} sub={`${summary.month.tool_calls} tool calls`} />
            <Tile label="Images Generated" value={summary.month.images.toLocaleString()} sub={summary.month.unpriced_calls ? `${summary.month.unpriced_calls} unpriced calls` : "all calls priced"} />
          </>
        ) : <p className="text-sm text-muted">Loading…</p>}
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_400px]">
        <div className="space-y-4">
          <Card>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <CardTitle>Breakdown</CardTitle>
              <div className="ml-auto flex gap-1">
                {DIMENSIONS.map((d) => <button key={d} onClick={() => setBy(d)} className={`rounded-full px-2.5 py-0.5 text-xs capitalize ${by === d ? "bg-accent text-accent-contrast" : "bg-surface-2 text-muted"}`}>By {d}</button>)}
              </div>
              <div className="w-32"><Select value={range} onChange={setRange} options={[{ value: "today", label: "Today" }, { value: "7d", label: "Last 7 days" }, { value: "month", label: "This month" }, { value: "30d", label: "Last 30 days" }]} /></div>
            </div>
            {rows.length === 0 ? <EmptyState title="No usage in this range" /> : (
              <table className="w-full text-xs">
                <thead className="text-left text-muted"><tr><th className="p-1.5 capitalize">{by}</th><th className="p-1.5 text-right">Cost</th><th className="p-1.5 text-right">Requests</th><th className="p-1.5 text-right">In</th><th className="p-1.5 text-right">Out</th><th className="p-1.5 text-right">Images</th><th className="p-1.5 text-right">Avg ms</th></tr></thead>
                <tbody>{rows.map((r) => <tr key={r.key ?? r.label} className="border-t border-border"><td className="p-1.5">{r.label}</td><td className="p-1.5 text-right">{money(r.cost_usd)}</td><td className="p-1.5 text-right">{r.requests}</td><td className="p-1.5 text-right">{r.input_tokens.toLocaleString()}</td><td className="p-1.5 text-right">{r.output_tokens.toLocaleString()}</td><td className="p-1.5 text-right">{r.images}</td><td className="p-1.5 text-right">{r.avg_latency_ms}</td></tr>)}</tbody>
              </table>
            )}
          </Card>
          <Card className="overflow-x-auto">
            <CardTitle>Recent calls</CardTitle>
            {calls.length === 0 ? <EmptyState title="No provider calls yet" /> : (
              <table className="w-full text-xs">
                <thead className="text-left text-muted"><tr><th className="p-1.5">When</th><th className="p-1.5">Agent</th><th className="p-1.5">Model</th><th className="p-1.5 text-right">Tokens</th><th className="p-1.5 text-right">Cost</th><th className="p-1.5 text-right">Latency</th><th className="p-1.5">Status</th></tr></thead>
                <tbody>{calls.map((c) => <tr key={c.id} className="border-t border-border"><td className="p-1.5 whitespace-nowrap">{new Date(c.created_at).toLocaleString()}</td><td className="p-1.5">{c.agent ?? "—"} <span className="text-muted">{c.command}</span></td><td className="p-1.5 font-mono">{c.provider_type}/{c.model}</td><td className="p-1.5 text-right">{c.input_tokens + c.output_tokens}{c.cached_input_tokens ? ` (${c.cached_input_tokens}c)` : ""}{c.images ? ` · ${c.images} img` : ""}</td><td className="p-1.5 text-right">{c.priced ? money(c.cost_usd) : <span className="text-warning">unpriced</span>}</td><td className="p-1.5 text-right">{c.latency_ms} ms</td><td className="p-1.5"><Badge tone={c.status === "ok" ? "success" : c.status === "error" ? "danger" : "neutral"}>{c.status}{c.error_code ? ` · ${c.error_code}` : ""}</Badge></td></tr>)}</tbody>
              </table>
            )}
          </Card>
        </div>
        <Card className="space-y-3">
          <CardTitle>Model pricing (USD per 1M tokens)</CardTitle>
          <p className="text-[11px] text-muted">Prices change; keep them here, not in code. Use a trailing * for a family (gpt-5*). Display currency and FX rate live in System Settings.</p>
          <ul className="divide-y divide-border text-xs">
            {pricing.map((p) => <li key={p.id} className="flex items-center justify-between py-1.5"><span><span className="font-mono">{p.provider_type}/{p.model}</span><span className="block text-muted">in ${p.input_per_million} · cached ${p.cached_input_per_million} · out ${p.output_per_million}{p.image_per_unit ? ` · image $${p.image_per_unit}` : ""}</span></span><span className="flex gap-2"><button className="text-accent" onClick={() => setForm({ provider_type: p.provider_type, model: p.model, input_per_million: String(p.input_per_million), cached_input_per_million: String(p.cached_input_per_million), output_per_million: String(p.output_per_million), image_per_unit: String(p.image_per_unit), note: p.note ?? "" })}>edit</button><button className="text-danger" onClick={() => void run(async () => { await api(`/admin/usage/pricing/${p.id}`, { method: "DELETE" }); load(); }, setError)}>remove</button></span></li>)}
            {pricing.length === 0 ? <li className="py-1.5 text-muted">No prices configured — costs will show as unpriced.</li> : null}
          </ul>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Provider"><Input value={form.provider_type} onChange={(e) => setForm({ ...form, provider_type: e.target.value })} /></Field>
            <Field label="Model or prefix*"><Input className="font-mono" value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} /></Field>
            <Field label="Input / 1M"><Input type="number" step="0.01" value={form.input_per_million} onChange={(e) => setForm({ ...form, input_per_million: e.target.value })} /></Field>
            <Field label="Cached input / 1M"><Input type="number" step="0.01" value={form.cached_input_per_million} onChange={(e) => setForm({ ...form, cached_input_per_million: e.target.value })} /></Field>
            <Field label="Output / 1M"><Input type="number" step="0.01" value={form.output_per_million} onChange={(e) => setForm({ ...form, output_per_million: e.target.value })} /></Field>
            <Field label="Image / unit"><Input type="number" step="0.001" value={form.image_per_unit} onChange={(e) => setForm({ ...form, image_per_unit: e.target.value })} /></Field>
          </div>
          <Field label="Note"><Input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="source / date of the price" /></Field>
          <Button onClick={() => void run(async () => { await api("/admin/usage/pricing", { method: "PUT", body: { provider_type: form.provider_type, model: form.model, input_per_million: Number(form.input_per_million || 0), cached_input_per_million: Number(form.cached_input_per_million || 0), output_per_million: Number(form.output_per_million || 0), image_per_unit: Number(form.image_per_unit || 0), note: form.note || null } }); load(); }, setError)}>Save price</Button>
          <ErrorText>{error}</ErrorText>
        </Card>
      </div>
    </AdminShell>
  );
}

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card>
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
      {sub ? <p className="text-[11px] text-faint">{sub}</p> : null}
    </Card>
  );
}
