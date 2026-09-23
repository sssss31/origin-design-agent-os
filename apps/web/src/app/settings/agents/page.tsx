"use client";

import { ArrowLeft, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Badge, Card, ErrorText } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Input";
import { JsonField, Select } from "@/components/ui/JsonField";
import { agentsApi } from "@/lib/api/admin";
import { api } from "@/lib/api/client";
import { useSession } from "@/lib/session";
import type { AgentSummaryOut, ProviderConnectionOut } from "@/types/admin";

const TYPES = [
  { value: "openai_responses", label: "OpenAI Responses API (GPT agent / prompt)" },
  { value: "http", label: "HTTP JSON endpoint" },
];

interface SettingsOut {
  default_agent_id: string | null;
}

/** Internal page: connect each GPT agent's endpoint + API key. Keys never come back to the browser. */
export default function AgentsSettingsPage() {
  const session = useSession();
  const router = useRouter();
  const [agents, setAgents] = useState<AgentSummaryOut[] | null>(null);
  const [editing, setEditing] = useState<AgentSummaryOut | "new" | null>(null);
  const [defaultAgent, setDefaultAgent] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => agentsApi.list().then((list) => setAgents(list.filter((a) => !a.is_manager))).catch(() => setAgents([])), []);
  useEffect(() => {
    if (session.status === "anonymous") router.replace("/login");
    if (session.status === "authenticated" && !session.me?.capabilities.admin_console) router.replace("/");
  }, [session.status, session.me, router]);
  useEffect(() => {
    if (session.status !== "authenticated") return;
    void load();
    api<SettingsOut>("/admin/settings").then((s) => setDefaultAgent(s.default_agent_id ?? "")).catch(() => undefined);
  }, [session.status, load]);
  const setDefault = async (id: string) => {
    setDefaultAgent(id);
    try {
      await api("/admin/settings", { method: "PUT", body: { default_agent_id: id || null } });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    }
  };
  if (session.status !== "authenticated") return null;
  return (
    <div className="min-h-screen bg-bg text-text">
      <div className="mx-auto max-w-3xl px-4 py-8">
        <Link href="/" className="mb-6 inline-flex items-center gap-1 text-sm text-muted hover:text-text"><ArrowLeft size={14} /> Back to chat</Link>
        <div className="mb-6 flex items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Agents & API keys</h1>
            <p className="mt-1 text-sm text-muted">Each agent is called directly with its own API key when someone types its /command. Keys are stored encrypted on the server.</p>
          </div>
          <Button onClick={() => setEditing("new")}><Plus size={14} /> Add agent</Button>
        </div>
        <ErrorText>{error}</ErrorText>
        {agents === null ? <p className="text-sm text-muted">Loading…</p> : null}
        {agents?.length === 0 ? (
          <Card>
            <p className="text-sm text-muted">No agents yet. Add one, or create the eight standard commands and fill in their keys.</p>
            <div className="mt-3"><Button variant="secondary" onClick={() => void agentsApi.seedRegistry("openai_responses").then(load).catch((e: Error) => setError(e.message))}>Create /master /resize /editable /qc /copy /asset /export /agent8</Button></div>
          </Card>
        ) : null}
        {agents?.length ? (
          <div className="mb-4 flex items-center gap-3 text-sm">
            <span className="text-muted">Default agent for plain messages</span>
            <div className="w-64"><Select value={defaultAgent} onChange={(v) => void setDefault(v)} options={[{ value: "", label: "First connected agent" }, ...agents.map((a) => ({ value: a.id, label: `${a.name} ${a.command}` }))]} /></div>
          </div>
        ) : null}
        <div className="space-y-2">
          {agents?.map((a) => {
            const c = a.connection;
            const tone = c?.connection_status === "ok" ? "success" : c?.connection_status === "error" ? "danger" : "neutral";
            return (
              <button key={a.id} onClick={() => setEditing(a)} className="flex w-full items-center gap-3 rounded-xl border border-border bg-surface px-4 py-3 text-left hover:border-border-strong">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-soft text-sm font-semibold text-accent">{a.name.slice(0, 1)}</span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium">{a.name} <span className="font-mono text-xs text-accent">{a.command}</span></span>
                  <span className="block truncate text-xs text-muted">{c?.api_endpoint || "No endpoint yet"}</span>
                </span>
                {c?.connection_type === "origin" ? (
                  <span className="text-xs text-faint">Origin-hosted</span>
                ) : c?.configured ? (
                  <span className="font-mono text-xs text-muted">{c.api_key_preview}</span>
                ) : (
                  <span className="text-xs text-warning">No API key</span>
                )}
                <Badge tone={tone}>{c?.connection_status === "ok" ? "Connected" : c?.connection_status === "error" ? "Failed" : "Untested"}</Badge>
                <Badge tone={a.status === "active" ? "success" : "neutral"}>{a.status}</Badge>
              </button>
            );
          })}
        </div>
      </div>
      {editing ? <AgentEditor agent={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); void load(); }} /> : null}
    </div>
  );
}

function AgentEditor({ agent, onClose, onSaved }: { agent: AgentSummaryOut | null; onClose: () => void; onSaved: () => void }) {
  const conn = agent?.connection ?? null;
  const [name, setName] = useState(agent?.name ?? "");
  const [command, setCommand] = useState(agent?.command ?? "/");
  const [description, setDescription] = useState(agent?.description ?? "");
  const [type, setType] = useState<string>(conn?.connection_type && conn.connection_type !== "origin" ? conn.connection_type : "openai_responses");
  const [endpoint, setEndpoint] = useState(conn?.api_endpoint ?? "https://api.openai.com/v1");
  const [apiKey, setApiKey] = useState("");
  const [config, setConfig] = useState<Record<string, unknown>>(conn?.config ?? {});
  const [advanced, setAdvanced] = useState(false);
  const [enabled, setEnabled] = useState(agent ? agent.status === "active" : true);
  const [test, setTest] = useState<ProviderConnectionOut | null>(null);
  const [busy, setBusy] = useState<"save" | "test" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const looksLikeCurl = /^\s*curl\s/i.test(apiKey);

  const persist = async (): Promise<string> => {
    let id = agent?.id;
    if (!id) id = (await agentsApi.create({ name, command, description })).id;
    else if (name !== agent?.name || command !== agent?.command || description !== agent?.description) await agentsApi.update(id, { name, command, description });
    await agentsApi.setConnection(id, { connection_type: type, api_endpoint: endpoint || null, api_key: apiKey || undefined, config });
    const status = enabled ? "active" : "disabled";
    if (!agent || agent.status !== status) await agentsApi.update(id, { status });
    setApiKey("");
    return id;
  };
  const save = async () => {
    setBusy("save");
    setError(null);
    try {
      await persist();
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusy(null);
    }
  };
  const runTest = async () => {
    setBusy("test");
    setError(null);
    try {
      const id = await persist();
      setTest(await agentsApi.testConnection(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/30 p-4" onClick={onClose}>
      <div className="max-h-[92vh] w-full max-w-xl overflow-y-auto rounded-2xl border border-border bg-surface p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-semibold">{agent ? `Edit ${agent.name}` : "Add agent"}</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Resize Agent" /></Field>
          <Field label="Command"><Input value={command} onChange={(e) => setCommand(e.target.value)} placeholder="/resize" /></Field>
          <div className="sm:col-span-2"><Field label="Description"><Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What this agent does (shown in the / menu)" /></Field></div>
          <div className="sm:col-span-2"><Select label="How is it called?" value={type} onChange={setType} options={TYPES} /></div>
          <div className="sm:col-span-2">
            <Field label="API endpoint" hint={type === "openai_responses" ? "Base URL; the adapter calls POST /responses with your prompt id from Options" : "Full URL that receives POST {message, session_id, history, files}"}>
              <Input value={endpoint} onChange={(e) => setEndpoint(e.target.value)} placeholder={type === "openai_responses" ? "https://api.openai.com/v1" : "https://agent.example.com/chat"} />
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Field label="API key" hint={conn?.configured ? `Configured · ${conn.api_key_preview} — leave empty to keep it` : "Paste the agent's key (or its cURL — only the Bearer token is kept)"}>
              <Input type="password" autoComplete="off" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={conn?.configured ? "Enter a new key to rotate" : "sk-…"} />
            </Field>
            {looksLikeCurl ? <p className="mt-1 text-xs text-warning">Looks like a cURL command — only the Bearer token will be stored.</p> : null}
          </div>
          <label className="flex items-center gap-2 text-sm sm:col-span-2"><input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /> Enabled (shown in the / menu)</label>
          <div className="sm:col-span-2">
            <button type="button" onClick={() => setAdvanced((v) => !v)} className="text-xs text-muted underline-offset-2 hover:underline">{advanced ? "Hide" : "Show"} advanced options</button>
            {advanced ? <div className="mt-2"><JsonField label={type === "openai_responses" ? "Options: model, prompt_id, prompt_version, store, timeout_seconds" : "Options: api_key_header, body_template, response_text_path, session_id_path, files_path, timeout_seconds"} value={config} onChange={setConfig} rows={5} /></div> : null}
          </div>
        </div>
        {test ? <p className={`mt-3 text-sm ${test.success ? "text-success" : "text-danger"}`}>{test.success ? "🟢" : "🔴"} {test.message} ({test.latency_ms} ms)</p> : null}
        <ErrorText>{error}</ErrorText>
        <div className="mt-5 flex items-center justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button variant="secondary" disabled={busy !== null || !name || !command} onClick={() => void runTest()}>{busy === "test" ? "Testing…" : "Test connection"}</Button>
          <Button disabled={busy !== null || !name || !command} onClick={() => void save()}>{busy === "save" ? "Saving…" : "Save"}</Button>
        </div>
      </div>
    </div>
  );
}
