"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AdminShell, useAsyncAction } from "@/components/admin/AdminShell";
import { KeyValueEditor } from "@/components/admin/KeyValueEditor";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardTitle, EmptyState, ErrorText } from "@/components/ui/Card";
import { Field, Input, Textarea } from "@/components/ui/Input";
import { Select } from "@/components/ui/JsonField";
import { agentsApi } from "@/lib/api/admin";
import { integrationsApi } from "@/lib/api/integrations";
import type { AgentSummaryOut } from "@/types/admin";
import type { CustomIntegrationOut, IntegrationTestOut } from "@/types/integrations";

const METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"];

export default function IntegrationDetailPage() {
  const { integrationId } = useParams<{ integrationId: string }>();
  const router = useRouter();
  const run = useAsyncAction();
  const [integ, setInteg] = useState<CustomIntegrationOut | null>(null);
  const [agents, setAgents] = useState<AgentSummaryOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const load = useCallback(() => Promise.all([integrationsApi.get(integrationId), agentsApi.list()]).then(([i, a]) => { setInteg(i); setAgents(a); }).catch((err: unknown) => setError(err instanceof Error ? err.message : "Could not load")), [integrationId]);
  useEffect(() => { void load(); }, [load]);
  const mutate = (fn: () => Promise<CustomIntegrationOut>, msg: string) => { setNotice(null); void run(async () => { setInteg(await fn()); setNotice(msg); }, setError); };
  if (!integ) return <AdminShell title="Custom API"><p className="text-sm text-muted">{error ?? "Loading…"}</p></AdminShell>;
  const health = integ.health_status === "ok" ? "success" : integ.health_status === "error" ? "danger" : "neutral";
  return (
    <AdminShell title={integ.name}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Badge tone={health}>{integ.health_status === "ok" ? "● Connected" : integ.health_status === "error" ? "● Connection Failed" : "○ Untested"}</Badge>
        <Badge tone={integ.status === "active" ? "success" : "neutral"}>{integ.status}</Badge>
        <span className="font-mono text-xs text-muted">{integ.method} {integ.endpoint}</span>
        {integ.tool_slug ? <Badge tone="accent">tool {integ.tool_slug}</Badge> : null}
        <div className="ml-auto flex gap-2">
          <Button variant="secondary" onClick={() => mutate(() => integrationsApi.update(integ.id, { status: integ.status === "active" ? "disabled" : "active" }), integ.status === "active" ? "Disabled" : "Enabled")}>{integ.status === "active" ? "Disable" : "Enable"}</Button>
          <Button variant="ghost" onClick={() => { if (window.confirm(`Delete ${integ.name} and its tool?`)) void run(async () => { await integrationsApi.remove(integ.id); router.push("/admin/integrations"); }, setError); }}>Delete</Button>
        </div>
      </div>
      <ErrorText>{error}</ErrorText>
      {notice ? <p className="mb-2 text-xs text-success">{notice}</p> : null}
      <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
        <div className="space-y-4">
          <RequestEditor integ={integ} onSave={(b) => mutate(() => integrationsApi.update(integ.id, b), "Saved — tool schema synced")} />
          <TestPanel integ={integ} onTested={() => void load()} />
        </div>
        <div className="space-y-4">
          <Card>
            <CardTitle>Status</CardTitle>
            <dl className="grid grid-cols-[130px_1fr] gap-y-1 text-xs">
              <dt className="text-muted">Authentication</dt><dd>{integ.secrets.length ? `•••••••• (${integ.auth_summary})` : "none"}</dd>
              <dt className="text-muted">Used by</dt><dd>{integ.used_by.join(", ") || "—"}</dd>
              <dt className="text-muted">Requests</dt><dd>{integ.request_count} ({integ.error_count} errors)</dd>
              <dt className="text-muted">Average latency</dt><dd>{integ.avg_latency_ms != null ? `${(integ.avg_latency_ms / 1000).toFixed(2)} sec` : "—"}</dd>
              <dt className="text-muted">Last test</dt><dd>{integ.last_tested_at ? new Date(integ.last_tested_at).toLocaleString() : "never"}{integ.health_message ? ` · ${integ.health_message}` : ""}</dd>
              <dt className="text-muted">Variables</dt><dd className="font-mono">{integ.variables.map((v) => `{{${v}}}`).join(" ") || "—"}</dd>
            </dl>
          </Card>
          <SecretsPanel integ={integ} mutate={mutate} />
          <AssignPanel integ={integ} agents={agents} onChanged={() => void load()} />
        </div>
      </div>
    </AdminShell>
  );
}

function RequestEditor({ integ, onSave }: { integ: CustomIntegrationOut; onSave: (b: Parameters<typeof integrationsApi.update>[1]) => void }) {
  const [name, setName] = useState(integ.name);
  const [description, setDescription] = useState(integ.description);
  const [method, setMethod] = useState(integ.method);
  const [endpoint, setEndpoint] = useState(integ.endpoint);
  const [headers, setHeaders] = useState(integ.headers_template);
  const [query, setQuery] = useState(integ.query_template);
  const [body, setBody] = useState(integ.body_template ?? "");
  const [ctype, setCtype] = useState(integ.content_type);
  const [timeout, setTimeoutS] = useState(String(integ.timeout_seconds));
  return (
    <Card className="space-y-3">
      <CardTitle>Request</CardTitle>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Description (tool description for agents)"><Input value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
      </div>
      <div className="grid gap-3 sm:grid-cols-[120px_1fr]">
        <Select label="Method" value={method} onChange={setMethod} options={METHODS.map((m) => ({ value: m, label: m }))} />
        <Field label="Endpoint"><Input className="font-mono text-xs" value={endpoint} onChange={(e) => setEndpoint(e.target.value)} /></Field>
      </div>
      <Field label="Headers"><KeyValueEditor value={headers} onChange={setHeaders} /></Field>
      <Field label="Query parameters"><KeyValueEditor value={query} onChange={setQuery} keyPlaceholder="param" valuePlaceholder="{{value}} or {{secrets.key}}" /></Field>
      {method !== "GET" ? (
        <>
          <Field label="Body template"><Textarea rows={8} className="font-mono text-xs" value={body} onChange={(e) => setBody(e.target.value)} /></Field>
          <div className="grid gap-3 sm:grid-cols-2"><Field label="Content-Type"><Input className="font-mono text-xs" value={ctype} onChange={(e) => setCtype(e.target.value)} /></Field><Field label="Timeout (s)"><Input type="number" min={1} max={300} value={timeout} onChange={(e) => setTimeoutS(e.target.value)} /></Field></div>
        </>
      ) : <Field label="Timeout (s)"><Input type="number" min={1} max={300} value={timeout} onChange={(e) => setTimeoutS(e.target.value)} /></Field>}
      <Button onClick={() => onSave({ name, description, method, endpoint, headers_template: headers, query_template: query, body_template: method === "GET" ? null : body, content_type: ctype, timeout_seconds: Number(timeout) })}>Save</Button>
    </Card>
  );
}

function SecretsPanel({ integ, mutate }: { integ: CustomIntegrationOut; mutate: (fn: () => Promise<CustomIntegrationOut>, msg: string) => void }) {
  const [name, setName] = useState(integ.missing_secrets[0] ?? "");
  const [value, setValue] = useState("");
  const [location, setLocation] = useState("header");
  return (
    <Card className="space-y-2">
      <CardTitle>Secrets</CardTitle>
      <p className="text-[11px] text-muted">Referenced from templates as <code>{"{{secrets.name}}"}</code>. Values are encrypted at rest and never shown again.</p>
      {integ.secrets.length === 0 && integ.missing_secrets.length === 0 ? <p className="text-xs text-muted">No secrets.</p> : null}
      <ul className="divide-y divide-border text-xs">
        {integ.secrets.map((s) => (
          <li key={s.name} className="flex items-center justify-between py-1.5">
            <span className="font-mono">{s.name} <span className="text-muted">{s.key_preview ?? "••••••••"}</span> <Badge>{s.location}</Badge>{s.rotated_at ? <span className="ml-1 text-faint">rotated {new Date(s.rotated_at).toLocaleDateString()}</span> : null}</span>
            <span className="flex gap-1"><button className="text-accent" onClick={() => { setName(s.name); setLocation(s.location); }}>rotate</button><button className="text-danger" onClick={() => mutate(() => integrationsApi.deleteSecret(integ.id, s.name), "Secret removed")}>remove</button></span>
          </li>
        ))}
        {integ.missing_secrets.map((m) => <li key={m} className="py-1.5 font-mono text-warning">{m} <Badge tone="warning">missing — referenced in template</Badge></li>)}
      </ul>
      <div className="grid grid-cols-[1fr_1fr] gap-1">
        <Input className="font-mono text-xs" placeholder="name" value={name} onChange={(e) => setName(e.target.value)} />
        <Select value={location} onChange={setLocation} options={["header", "query", "basic", "body", "cookie"].map((l) => ({ value: l, label: l }))} />
      </div>
      <Input type="password" autoComplete="off" placeholder="value (write-only)" value={value} onChange={(e) => setValue(e.target.value)} />
      <Button variant="secondary" disabled={!name || !value} onClick={() => { mutate(() => integrationsApi.setSecret(integ.id, { name, value, location }), `Secret ${name} stored`); setValue(""); }}>Save secret</Button>
    </Card>
  );
}

function TestPanel({ integ, onTested }: { integ: CustomIntegrationOut; onTested: () => void }) {
  const [vars, setVars] = useState<Record<string, string>>(() => Object.fromEntries(integ.variables.map((v) => [v, v === "workspace_id" ? "demo" : v === "prompt" ? "Test design" : ""])));
  const [result, setResult] = useState<IntegrationTestOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const runTest = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await integrationsApi.test(integ.id, vars));
      onTested();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card className="space-y-3">
      <CardTitle>Test API</CardTitle>
      {integ.variables.length ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {integ.variables.map((v) => <Field key={v} label={v}><Input value={vars[v] ?? ""} onChange={(e) => setVars({ ...vars, [v]: e.target.value })} /></Field>)}
        </div>
      ) : <p className="text-xs text-muted">This request has no variables.</p>}
      <Button disabled={busy || integ.missing_secrets.length > 0} onClick={() => void runTest()}>{busy ? "Calling…" : "Send test request"}</Button>
      {integ.missing_secrets.length ? <p className="text-xs text-warning">Add the missing secret(s) before testing.</p> : null}
      <ErrorText>{error}</ErrorText>
      {result ? (
        <div className="grid gap-3 md:grid-cols-[1fr_auto_1fr] items-start text-xs">
          <div className="rounded-md border border-border p-2">
            <p className="mb-1 font-medium">Request</p>
            <pre className="whitespace-pre-wrap">{`${result.request.method ?? integ.method} ${result.request.url ?? ""}\n${Object.entries(result.request.headers ?? {}).map(([k, v]) => `${k}: ${v}`).join("\n")}${result.request.body ? `\n\n${result.request.body}` : ""}${result.request.error ? `\n! ${result.request.error}` : ""}`}</pre>
          </div>
          <div className="self-center text-center text-muted">→ API →</div>
          <div className={`rounded-md border p-2 ${result.ok ? "border-success/40" : "border-danger/40"}`}>
            <p className="mb-1 font-medium">Response {result.ok ? "🟢" : "🔴"}</p>
            <dl className="mb-1 grid grid-cols-[90px_1fr] gap-y-0.5">
              <dt className="text-muted">HTTP status</dt><dd>{result.status ?? "—"}</dd>
              <dt className="text-muted">Latency</dt><dd>{result.latency_ms} ms</dd>
              <dt className="text-muted">Size</dt><dd>{result.response_size_bytes != null ? `${result.response_size_bytes} bytes` : "—"}</dd>
              <dt className="text-muted">Type</dt><dd>{result.content_type ?? "—"}</dd>
            </dl>
            {result.error_message ? <p className="text-danger">{result.error_code}: {result.error_message}</p> : null}
            {result.file ? <p>Binary response stored as file <code>{result.file}</code></p> : <pre className="max-h-60 overflow-auto whitespace-pre-wrap">{typeof result.response_preview === "string" ? result.response_preview : JSON.stringify(result.response_preview, null, 2)}</pre>}
          </div>
        </div>
      ) : null}
    </Card>
  );
}

function AssignPanel({ integ, agents, onChanged }: { integ: CustomIntegrationOut; agents: AgentSummaryOut[]; onChanged: () => void }) {
  const run = useAsyncAction();
  const [error, setError] = useState<string | null>(null);
  const [agentId, setAgentId] = useState("");
  if (!integ.tool_id) return <Card><CardTitle>Assign to agents</CardTitle><EmptyState title="No tool" body="Save the integration to create its tool." /></Card>;
  return (
    <Card className="space-y-2">
      <CardTitle>Assign to agents</CardTitle>
      <p className="text-[11px] text-muted">Binds the tool <code>{integ.tool_slug}</code> to the agent&apos;s draft; publish the agent to make it live.</p>
      <ul className="text-xs">{integ.used_by.map((n) => <li key={n}>✓ {n}</li>)}{integ.used_by.length === 0 ? <li className="text-muted">Not assigned to any published agent yet.</li> : null}</ul>
      <div className="flex gap-1">
        <Select value={agentId} onChange={setAgentId} options={[{ value: "", label: "Choose agent…" }, ...agents.map((a) => ({ value: a.id, label: `${a.name} ${a.command}` }))]} />
        <Button variant="secondary" disabled={!agentId} onClick={() => void run(async () => { await agentsApi.attachTool(agentId, integ.tool_id!, {}); setAgentId(""); onChanged(); }, setError)}>Add</Button>
      </div>
      <ErrorText>{error}</ErrorText>
    </Card>
  );
}
