"use client";

import { Check, Loader2, X } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardTitle, ErrorText } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Input";
import { providersApi } from "@/lib/api/admin";
import type { ProviderConnectionOut, ProviderOut } from "@/types/admin";

const STEPS = ["Enter API key", "Test connection", "Choose allowed models", "Configure usage limits", "Save"];

/** Spec §21: first-time OpenAI configuration. The key is sent once and never read back. */
export function OpenAIConnectWizard({ existing, onDone, onCancel }: { existing?: ProviderOut | null; onDone: (p: ProviderOut) => void; onCancel: () => void }) {
  const [step, setStep] = useState(0);
  const [name, setName] = useState(existing?.name ?? "OpenAI Production");
  const [environment, setEnvironment] = useState(existing?.environment ?? "production");
  const [apiKey, setApiKey] = useState("");
  const [provider, setProvider] = useState<ProviderOut | null>(existing ?? null);
  const [test, setTest] = useState<ProviderConnectionOut | null>(null);
  const [visible, setVisible] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>(existing?.models.map((m) => m.model) ?? []);
  const [defaultModel, setDefaultModel] = useState(existing?.default_model ?? "");
  const [monthlyBudget, setMonthlyBudget] = useState(String((existing?.rate_limit_policy?.monthly_budget_usd as number | undefined) ?? ""));
  const [dailyRequests, setDailyRequests] = useState(String((existing?.rate_limit_policy?.max_requests_per_day as number | undefined) ?? ""));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const guard = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  };

  const saveKey = () =>
    guard(async () => {
      let p = provider;
      if (!p) p = await providersApi.create({ name, type: "openai", environment });
      else if (p.name !== name || p.environment !== environment) p = await providersApi.update(p.id, { name, environment });
      if (apiKey) p = await providersApi.setSecret(p.id, apiKey);
      setApiKey("");
      setProvider(p);
      setStep(1);
    });

  const runTest = () =>
    guard(async () => {
      if (!provider) return;
      const t = await providersApi.connectionTest(provider.id);
      setTest(t);
      if (t.success) {
        setVisible(t.available_models);
        if (selected.length === 0) setSelected(t.available_models.filter((m) => /^(gpt-5|gpt-4\.1|gpt-4o|o4|gpt-image)/.test(m)).slice(0, 12));
        setStep(2);
      }
    });

  const saveModels = () =>
    guard(async () => {
      if (!provider) return;
      const p = await providersApi.setModels(provider.id, selected.map((model) => ({ model })), defaultModel || selected[0] || null);
      setProvider(p);
      setStep(3);
    });

  const finish = () =>
    guard(async () => {
      if (!provider) return;
      const policy: Record<string, number> = {};
      if (monthlyBudget) policy.monthly_budget_usd = Number(monthlyBudget);
      if (dailyRequests) policy.max_requests_per_day = Number(dailyRequests);
      const p = await providersApi.update(provider.id, { rate_limit_policy: policy, enabled: true });
      setProvider(p);
      setStep(4);
      onDone(p);
    });

  const toggle = (m: string) => setSelected((s) => (s.includes(m) ? s.filter((x) => x !== m) : [...s, m]));
  const candidates = Array.from(new Set([...visible, ...selected])).sort();

  return (
    <Card className="space-y-4">
      <div className="flex items-center justify-between">
        <CardTitle>Connect OpenAI</CardTitle>
        <button onClick={onCancel} className="text-muted hover:text-text" aria-label="Close"><X size={16} /></button>
      </div>
      <ol className="flex flex-wrap gap-2 text-xs">
        {STEPS.map((label, i) => (
          <li key={label} className={`flex items-center gap-1 rounded-full px-2 py-0.5 ${i === step ? "bg-accent text-accent-contrast" : i < step ? "bg-success/15 text-success" : "bg-surface-2 text-muted"}`}>
            {i < step ? <Check size={11} /> : <span>{i + 1}.</span>} {label}
          </li>
        ))}
      </ol>
      {step === 0 ? (
        <div className="space-y-3">
          <Field label="Provider name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Environment">
            <select className="w-full rounded-md border border-border bg-surface px-2 py-2 text-sm" value={environment} onChange={(e) => setEnvironment(e.target.value as ProviderOut["environment"])} aria-label="Environment">
              <option value="production">Production</option>
              <option value="staging">Staging</option>
              <option value="development">Development</option>
            </select>
          </Field>
          <Field label="API key" hint="Sent once to the server, encrypted at rest, never shown again.">
            <Input type="password" autoComplete="off" placeholder={provider?.has_secret ? `Stored: ${provider.key_preview} — paste a new key to rotate` : "sk-proj-…"} value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
          </Field>
          <Button disabled={busy || (!apiKey && !provider?.has_secret) || (apiKey.length > 0 && apiKey.length < 20)} onClick={() => void saveKey()}>{busy ? <Loader2 size={14} className="animate-spin" /> : null} {provider?.has_secret && !apiKey ? "Keep stored key" : "Save key"}</Button>
        </div>
      ) : null}
      {step === 1 ? (
        <div className="space-y-3">
          <p className="text-sm text-muted">Key stored as <span className="font-mono">{provider?.key_preview}</span>. Run a minimal authenticated request to verify it.</p>
          {test ? <p className={`text-sm ${test.success ? "text-success" : "text-danger"}`}>{test.success ? "🟢 Connected" : "🔴 Connection Failed"} — {test.message} ({test.latency_ms} ms)</p> : null}
          <div className="flex gap-2">
            <Button disabled={busy} onClick={() => void runTest()}>{busy ? "Testing…" : "Test connection"}</Button>
            <Button variant="ghost" onClick={() => setStep(0)}>Change key</Button>
          </div>
        </div>
      ) : null}
      {step === 2 ? (
        <div className="space-y-3">
          <p className="text-sm text-muted">{visible.length} models visible to this key. Allow the ones agents may use.</p>
          <div className="grid max-h-60 gap-1 overflow-y-auto rounded-md border border-border p-2 sm:grid-cols-2 lg:grid-cols-3">
            {candidates.map((m) => (
              <label key={m} className="flex items-center gap-2 text-xs"><input type="checkbox" checked={selected.includes(m)} onChange={() => toggle(m)} /> <span className="font-mono">{m}</span></label>
            ))}
          </div>
          <Field label="Default model"><Input list="wizard-models" value={defaultModel} onChange={(e) => setDefaultModel(e.target.value)} placeholder={selected[0] ?? ""} /></Field>
          <datalist id="wizard-models">{selected.map((m) => <option key={m} value={m} />)}</datalist>
          <Button disabled={busy || selected.length === 0} onClick={() => void saveModels()}>Save {selected.length} models</Button>
        </div>
      ) : null}
      {step === 3 ? (
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Monthly budget (USD)" hint="Runs are refused once the month's estimated spend exceeds this."><Input type="number" min={0} value={monthlyBudget} onChange={(e) => setMonthlyBudget(e.target.value)} placeholder="unlimited" /></Field>
            <Field label="Max requests per day"><Input type="number" min={0} value={dailyRequests} onChange={(e) => setDailyRequests(e.target.value)} placeholder="unlimited" /></Field>
          </div>
          <Button disabled={busy} onClick={() => void finish()}>Save & enable</Button>
        </div>
      ) : null}
      {step === 4 ? (
        <div className="space-y-2">
          <p className="text-sm font-medium text-success">✓ OpenAI Connected</p>
          <p className="text-sm text-muted">Origin agents can now use this provider. Assign it under Agents → Edit Agent → AI Provider.</p>
          <div className="flex gap-2"><Badge tone="success">{provider?.key_preview}</Badge><Badge>{provider?.models.length ?? 0} models</Badge></div>
          <Button variant="secondary" onClick={onCancel}>Close</Button>
        </div>
      ) : null}
      <ErrorText>{error}</ErrorText>
    </Card>
  );
}
