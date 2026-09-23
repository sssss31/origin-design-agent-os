"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { KeyValueEditor } from "@/components/admin/KeyValueEditor";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardTitle, ErrorText } from "@/components/ui/Card";
import { Field, Input, Textarea } from "@/components/ui/Input";
import { Select } from "@/components/ui/JsonField";
import { integrationsApi } from "@/lib/api/integrations";
import type { CurlPreview } from "@/types/integrations";

const METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"];
const EXAMPLE = `curl https://api.example.com/v1/process \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"prompt": "{{prompt}}", "workspace_id": "{{workspace_id}}"}'`;

/** Admin → API Integrations → Add Custom API (spec §7–§8). */
export default function NewIntegrationPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"form" | "curl">("curl");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [curl, setCurl] = useState("");
  const [preview, setPreview] = useState<CurlPreview | null>(null);
  const [method, setMethod] = useState("POST");
  const [endpoint, setEndpoint] = useState("https://api.example.com/v1/generate");
  const [headers, setHeaders] = useState<Record<string, string>>({ Authorization: "Bearer {{secrets.api_key}}", "Content-Type": "application/json" });
  const [body, setBody] = useState('{\n  "prompt": "{{prompt}}",\n  "workspace_id": "{{workspace_id}}",\n  "asset_url": "{{asset_url}}"\n}');
  const [timeout, setTimeoutS] = useState("30");
  const [secretName, setSecretName] = useState("api_key");
  const [secretValue, setSecretValue] = useState("");
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

  return (
    <AdminShell title="Add Custom API">
      <div className="mb-3 flex gap-1 rounded-lg border border-border bg-surface p-0.5 w-fit">
        {(["curl", "form"] as const).map((m) => (
          <button key={m} onClick={() => setMode(m)} className={`rounded-md px-3 py-1 text-xs font-medium ${mode === m ? "bg-accent-soft text-accent" : "text-muted hover:text-text"}`}>{m === "curl" ? "Import from cURL" : "Configure manually"}</button>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <Card className="space-y-3">
          <Field label="Integration name"><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Internal SVG Engine" /></Field>
          <Field label="Description"><Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What this API does (shown to agents as the tool description)" /></Field>
          {mode === "curl" ? (
            <>
              <Field label="Paste a cURL command" hint="Credentials found in headers, query strings, -u or JSON fields are moved into encrypted secret storage. The raw command is never saved.">
                <Textarea rows={10} className="font-mono text-xs" value={curl} onChange={(e) => { setCurl(e.target.value); setPreview(null); }} placeholder={EXAMPLE} />
              </Field>
              <div className="flex gap-2">
                <Button variant="secondary" disabled={busy || curl.trim().length < 8} onClick={() => void guard(async () => setPreview(await integrationsApi.parseCurl(curl)))}>Preview</Button>
                <Button disabled={busy || !name.trim() || curl.trim().length < 8} onClick={() => void guard(async () => { const c = await integrationsApi.importCurl({ curl, name, description }); router.push(`/admin/integrations/custom/${c.id}`); })}>Import & create</Button>
              </div>
            </>
          ) : (
            <>
              <div className="grid gap-3 sm:grid-cols-[120px_1fr]">
                <Select label="Method" value={method} onChange={setMethod} options={METHODS.map((m) => ({ value: m, label: m }))} />
                <Field label="Endpoint" hint="https only (public hosts). Placeholders such as {{id}} are allowed in the path."><Input className="font-mono text-xs" value={endpoint} onChange={(e) => setEndpoint(e.target.value)} /></Field>
              </div>
              <Field label="Headers"><KeyValueEditor value={headers} onChange={setHeaders} /></Field>
              {method !== "GET" ? <Field label="Body template" hint="Use {{prompt}}, {{workspace_id}}, {{asset_url}}… and {{secrets.name}} for credentials."><Textarea rows={8} className="font-mono text-xs" value={body} onChange={(e) => setBody(e.target.value)} /></Field> : null}
              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="Timeout (s)"><Input type="number" min={1} max={300} value={timeout} onChange={(e) => setTimeoutS(e.target.value)} /></Field>
                <Field label="Secret name"><Input className="font-mono text-xs" value={secretName} onChange={(e) => setSecretName(e.target.value)} /></Field>
                <Field label="Secret value (write-only)"><Input type="password" autoComplete="off" value={secretValue} onChange={(e) => setSecretValue(e.target.value)} placeholder="stored encrypted" /></Field>
              </div>
              <Button disabled={busy || !name.trim() || !endpoint.trim()} onClick={() => void guard(async () => { const c = await integrationsApi.create({ name, description, method, endpoint, headers_template: headers, body_template: method === "GET" ? null : body, timeout_seconds: Number(timeout), secrets: secretValue ? [{ name: secretName, value: secretValue }] : [] }); router.push(`/admin/integrations/custom/${c.id}`); })}>Create integration</Button>
            </>
          )}
          <ErrorText>{error}</ErrorText>
        </Card>
        <Card>
          <CardTitle>{preview ? "Import preview" : "How it works"}</CardTitle>
          {preview ? (
            <div className="space-y-2 text-xs">
              <dl className="grid grid-cols-[100px_1fr] gap-y-1">
                {Object.entries(preview.summary).map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="capitalize text-muted">{k}</dt>
                    <dd className="font-mono">{v}</dd>
                  </div>
                ))}
              </dl>
              <div>
                <p className="mb-1 font-medium">Secrets detected</p>
                {preview.secrets.length === 0 ? <p className="text-muted">none</p> : preview.secrets.map((s) => <p key={s.name + s.location} className="font-mono">{"{{secrets." + s.name + "}}"} <Badge>{s.location}</Badge> <span className="text-muted">{s.preview}</span></p>)}
              </div>
              <div>
                <p className="mb-1 font-medium">Variables</p>
                <p className="font-mono">{preview.variables.length ? preview.variables.map((v) => `{{${v}}}`).join("  ") : "none — add {{prompt}} placeholders to the body"}</p>
              </div>
              <div>
                <p className="mb-1 font-medium">Headers (templated)</p>
                <pre className="whitespace-pre-wrap rounded bg-surface-2 p-2">{Object.entries(preview.headers).map(([k, v]) => `${k}: ${v}`).join("\n") || "—"}</pre>
              </div>
              {preview.body ? <div><p className="mb-1 font-medium">Body template</p><pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-surface-2 p-2">{preview.body}</pre></div> : null}
              {preview.warnings.map((w) => <p key={w} className="text-warning">⚠ {w}</p>)}
            </div>
          ) : (
            <ol className="list-decimal space-y-1 pl-4 text-xs text-muted">
              <li>Paste a cURL or fill the form. Placeholders like <code>{"{{prompt}}"}</code> become tool inputs.</li>
              <li>Credentials are stored encrypted and referenced as <code>{"{{secrets.name}}"}</code>.</li>
              <li>A tool <code>api.&lt;slug&gt;</code> is created automatically; bind it to agents under Agents → Tools.</li>
              <li>Test the API with sample variables before agents use it.</li>
            </ol>
          )}
        </Card>
      </div>
    </AdminShell>
  );
}
