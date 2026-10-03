"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { ConnectionForm, emptyDraft, type ConnectionDraft } from "@/components/admin/ConnectionForm";
import { ConnectionBadge, RunBadge, RuntimeBadge, typeLabel } from "@/components/admin/StatusBadge";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardTitle, EmptyState, ErrorText } from "@/components/ui/Card";
import { Field, Input, Textarea } from "@/components/ui/Input";
import { Tabs } from "@/components/ui/Tabs";
import { agentsApi, consoleApi } from "@/lib/api/admin";
import type { ActivityRunOut, AgentMessageTestOut, AgentOut, ExecutionMode, NativeTestOut, ProviderConnectionOut } from "@/types/admin";

type Tab = "connection" | "runtime" | "test" | "activity" | "settings";
const TABS: { id: Tab; label: string }[] = [
  { id: "connection", label: "Connection" },
  { id: "runtime", label: "Runtime" },
  { id: "test", label: "Test" },
  { id: "activity", label: "Activity" },
  { id: "settings", label: "Settings" },
];

export default function AgentDetailPage() {
  const { agentId } = useParams<{ agentId: string }>();
  const [agent, setAgent] = useState<AgentOut | null>(null);
  const [tab, setTab] = useState<Tab>("connection");
  // the connection draft lives here so a typed key survives switching to Test/Activity and back
  const [draft, setDraft] = useState<ConnectionDraft | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => agentsApi.get(agentId).then(setAgent).catch((e: Error) => setError(e.message)), [agentId]);
  useEffect(() => {
    void load();
  }, [load]);
  const mutate = async (fn: () => Promise<AgentOut>, msg: string) => {
    setError(null);
    setNotice(null);
    try {
      setAgent(await fn());
      setNotice(msg);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    }
  };
  if (!agent) return <AdminShell title="Agent"><p className="text-sm text-muted">{error ?? "Loading…"}</p></AdminShell>;
  const isOrigin = !agent.connection || agent.connection.connection_type === "origin";
  return (
    <AdminShell title={`${agent.name} ${agent.command}`}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <ConnectionBadge agent={agent} />
        <RuntimeBadge agent={agent} />
        <Badge tone={agent.status === "active" ? "success" : "neutral"}>{agent.status === "active" ? "enabled" : agent.status}</Badge>
        <span className="text-xs text-muted">{typeLabel(agent.connection?.connection_type)}{agent.connection?.api_endpoint ? ` · ${agent.connection.api_endpoint}` : ""}</span>
        {agent.connection?.connection_message && agent.connection.connection_status !== "unknown" ? <span className="text-xs text-faint">— {agent.connection.connection_message}</span> : null}
        <Link href={`/admin/agents/${agent.id}/advanced`} className="ml-auto text-xs text-muted hover:text-text">Advanced editor →</Link>
      </div>
      <Tabs tabs={TABS} value={tab} onChange={setTab} />
      {notice ? <p className="mt-2 text-xs text-success">{notice}</p> : null}
      <ErrorText>{error}</ErrorText>
      <div className="mt-3">
        {tab === "connection" ? <ConnectionTab agent={agent} isOrigin={isOrigin} mutate={mutate} draft={draft ?? emptyDraft(agent.connection)} setDraft={setDraft} /> : null}
        {tab === "runtime" ? <RuntimeTab agent={agent} mutate={mutate} /> : null}
        {tab === "test" ? <TestTab agent={agent} onTested={load} /> : null}
        {tab === "activity" ? <ActivityTab agentId={agent.id} /> : null}
        {tab === "settings" ? <SettingsTab agent={agent} mutate={mutate} /> : null}
      </div>
    </AdminShell>
  );
}

function ConnectionTab({ agent, isOrigin, mutate, draft, setDraft }: { agent: AgentOut; isOrigin: boolean; mutate: (fn: () => Promise<AgentOut>, msg: string) => Promise<void>; draft: ConnectionDraft; setDraft: (d: ConnectionDraft | null) => void }) {
  const [test, setTest] = useState<ProviderConnectionOut | null>(null);
  const [busy, setBusy] = useState<"save" | "test" | null>(null);
  const keyTyped = draft.api_key.trim().length > 0;
  /** Returns false when the server refused the change (the typed key is kept so it can be corrected). */
  const save = async (): Promise<boolean> => {
    setBusy("save");
    const result = { saved: false };
    const before = agent.connection?.api_key_preview ?? null;
    await mutate(async () => {
      const out = await agentsApi.setConnection(agent.id, { connection_type: draft.connection_type, api_endpoint: draft.api_endpoint || null, api_key: draft.api_key || undefined, config: draft.config });
      result.saved = true;
      return out;
    }, keyTyped ? "Connection saved — access token updated" : agent.connection?.configured ? `Connection saved — access token unchanged (${before ?? "configured"})` : "Connection saved — no access token set yet");
    setBusy(null);
    if (!result.saved) return false;
    setDraft(null); // rebuild from the saved agent; the key field is write-only
    return true;
  };
  const runTest = async () => {
    setBusy("test");
    try {
      if (keyTyped || draft.api_endpoint !== (agent.connection?.api_endpoint ?? "")) {
        if (!(await save())) return;
      }
      setTest(await agentsApi.testConnection(agent.id));
      await mutate(() => agentsApi.get(agent.id), "Connection tested");
    } catch (err) {
      setTest({ success: false, provider: draft.connection_type, status: "failed", message: err instanceof Error ? err.message : "Test failed", latency_ms: 0, available_models: [], tested_at: new Date().toISOString() });
    } finally {
      setBusy(null);
    }
  };
  return (
    <Card>
      <CardTitle>API connection</CardTitle>
      {isOrigin ? <p className="mb-3 text-xs text-muted">This agent currently runs inside Origin (AI provider + instructions from the Advanced editor). Choose a connection type below to point it at an external GPT agent instead.</p> : null}
      <ConnectionForm draft={draft} onChange={setDraft} existing={agent.connection} />
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button disabled={busy !== null} onClick={() => void save()}>{busy === "save" ? "Saving…" : keyTyped ? "Save new token" : "Save"}</Button>
        <Button variant="secondary" disabled={busy !== null} onClick={() => void runTest()}>{busy === "test" ? "Testing…" : "Test connection"}</Button>
        {test ? <span className={`text-xs ${test.success ? "text-success" : "text-danger"}`}>{test.success ? "🟢" : "🔴"} {test.message} ({test.latency_ms} ms)</span> : null}
      </div>
    </Card>
  );
}

/**
 * Execution brief §8/§24/§25: which runtime answers inside Origin. A ChatGPT Workspace agent can keep
 * running in ChatGPT (result stays there) or run through Origin's native runtime (text/images/files
 * come back into this workspace). Native mode is only offered once the runtime has been tested.
 */
function RuntimeTab({ agent, mutate }: { agent: AgentOut; mutate: (fn: () => Promise<AgentOut>, msg: string) => Promise<void> }) {
  const rt = agent.runtime;
  const isWorkspace = agent.connection?.connection_type === "chatgpt_workspace";
  const [mode, setMode] = useState<ExecutionMode>(rt?.execution_mode ?? "origin_native");
  const [config, setConfig] = useState<Record<string, unknown>>(rt?.native_config ?? {});
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState<"save" | "test" | null>(null);
  const [prompt, setPrompt] = useState("resize 16:9");
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<NativeTestOut | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const str = (k: string) => (config[k] == null ? "" : String(config[k]));
  const set = (k: string, v: unknown) => setConfig((c) => { const n = { ...c }; if (v === "" || v == null) delete n[k]; else n[k] = v; return n; });
  const imageGen = config.image_generation !== false;
  if (!isWorkspace) {
    return (
      <Card>
        <CardTitle>Runtime</CardTitle>
        <p className="text-sm text-muted">This connection already returns its reply, images and files to Origin (<span className="font-mono">origin_native</span>). The Runtime tab only applies to ChatGPT Workspace Agents, whose API keeps the result inside ChatGPT.</p>
      </Card>
    );
  }
  const save = async (nextMode: ExecutionMode = mode) => {
    setBusy("save");
    await mutate(() => agentsApi.setRuntime(agent.id, { execution_mode: nextMode, native_config: config, native_api_key: key.trim() || undefined }), nextMode === "origin_native" ? "Runtime saved — this agent now answers inside Origin" : "Runtime saved");
    setKey("");
    setBusy(null);
  };
  const runTest = async () => {
    setBusy("test");
    setTestError(null);
    setResult(null);
    try {
      if (key.trim() || JSON.stringify(config) !== JSON.stringify(rt?.native_config ?? {})) await save(mode);
      setResult(await agentsApi.testNative(agent.id, prompt, file));
    } catch (err) {
      setTestError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setBusy(null);
    }
  };
  const nativeReady = (rt?.native_configured || key.trim().length > 0) && Boolean(config.model || config.prompt_id);
  const lastTest = (rt?.native_config.last_test as { ok?: boolean; at?: string; images?: number } | undefined) ?? null;
  const summary: { label: string; value: string; ok: boolean }[] = [
    { label: "Runtime", value: rt?.execution_mode === "origin_native" ? "Origin Native" : "Workspace Trigger (legacy)", ok: rt?.execution_mode === "origin_native" },
    { label: "Model", value: str("model") || "not set", ok: Boolean(str("model")) },
    { label: "Image model", value: str("image_model") || "API default", ok: true },
    { label: "Instructions", value: str("instructions").trim() ? "Configured" : "Missing", ok: Boolean(str("instructions").trim()) },
    { label: "API credential", value: rt?.native_configured ? "Configured" : "Missing", ok: Boolean(rt?.native_configured) },
    { label: "Image input", value: "Enabled", ok: true },
    { label: "Image generation", value: imageGen ? "Enabled" : "Disabled", ok: imageGen },
    { label: "Status", value: lastTest?.ok ? `Ready · tested ${new Date(lastTest.at ?? "").toLocaleString()}` : nativeReady ? "Configured — run Test Runtime" : "Not configured", ok: Boolean(lastTest?.ok) },
  ];
  return (
    <div className="space-y-3">
      <Card>
        <CardTitle>Origin-controlled runtime</CardTitle>
        <p className="mb-2 text-xs text-muted">This is Origin&apos;s own runtime (OpenAI Responses API) configured with {agent.name}&apos;s instructions, model and image settings so Origin receives the output. It is not the ChatGPT Workspace Agent instance itself; that stays available as the legacy Workspace Trigger.</p>
        <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
          {summary.map((row) => (
            <div key={row.label} className="flex items-center justify-between gap-3 border-b border-border/60 py-1">
              <dt className="text-muted">{row.label}</dt>
              <dd className={`text-right ${row.ok ? "" : "text-warning"}`}>{row.value}</dd>
            </div>
          ))}
        </dl>
      </Card>
      <Card>
        <CardTitle>Execution mode</CardTitle>
        <div className="grid gap-2 sm:grid-cols-2">
          <label className={`cursor-pointer rounded-xl border p-3 ${mode === "workspace_trigger" ? "border-accent bg-accent-soft/40" : "border-border"}`}>
            <span className="flex items-center gap-2 text-sm font-medium"><input type="radio" name="execution_mode" checked={mode === "workspace_trigger"} onChange={() => setMode("workspace_trigger")} /> Workspace Trigger</span>
            <p className="mt-1 text-xs text-muted">Runs the existing Workspace Agent{rt?.workspace_agent_id ? <> (<span className="font-mono">{rt.workspace_agent_id}</span>)</> : null}. The result stays in ChatGPT — the Workspace Agents API returns status only, not the reply or its images.</p>
          </label>
          <label className={`cursor-pointer rounded-xl border p-3 ${mode === "origin_native" ? "border-accent bg-accent-soft/40" : "border-border"} ${!rt?.native_available && !nativeReady ? "opacity-60" : ""}`}>
            <span className="flex items-center gap-2 text-sm font-medium"><input type="radio" name="execution_mode" checked={mode === "origin_native"} disabled={!rt?.native_available && !nativeReady} onChange={() => setMode("origin_native")} /> Origin Native</span>
            <p className="mt-1 text-xs text-muted">Runs the agent through Origin&apos;s runtime (OpenAI Responses API) with the instructions below. Text, images and files come back directly into this workspace.{!rt?.native_available ? " Configure and test the native runtime first." : ""}</p>
          </label>
        </div>
        <div className="mt-3 flex items-center gap-2">
          <Button disabled={busy !== null || (mode === "origin_native" && !nativeReady)} onClick={() => void save()}>{busy === "save" ? "Saving…" : mode === "origin_native" ? "Save & use Origin Native" : "Save"}</Button>
          <span className="text-xs text-muted">Current: <span className="font-mono">{rt?.execution_mode}</span></span>
        </div>
      </Card>
      <Card>
        <CardTitle>Native runtime</CardTitle>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Model" hint="gpt-5 or gpt-4.1 (image generation needs one of these)"><Input value={str("model")} placeholder="gpt-5" onChange={(e) => set("model", e.target.value)} /></Field>
          <Field label="OpenAI Platform API key" hint={rt?.native_configured ? `Configured · ${rt.native_api_key_preview} — leave empty to keep it` : "sk-… from platform.openai.com (billing on). Not a ChatGPT access token. Stored encrypted."}>
            <Input type="password" autoComplete="off" value={key} placeholder={rt?.native_configured ? "Enter a new key to rotate" : "sk-…"} onChange={(e) => setKey(e.target.value)} />
          </Field>
          <div className="sm:col-span-2">
            <Field label="Instructions" hint="The agent's approved instructions from ChatGPT, verbatim — this is what makes it the same agent.">
              <Textarea rows={8} value={str("instructions")} placeholder="You are Resize2. Given a design and a target ratio…" onChange={(e) => set("instructions", e.target.value)} />
            </Field>
          </div>
          <Field label="Image model" hint="gpt-image-2.5-sunburst (precise editing, recommended for resizes) · gpt-image-2.5-flare (fast) · gpt-image-2 · gpt-image-1.5">
            <Input value={str("image_model")} placeholder="gpt-image-2.5-sunburst" onChange={(e) => set("image_model", e.target.value)} />
          </Field>
          <Field label="Image action" hint="auto lets the model edit the source image or generate; edit forces an edit of the attached image">
            <select className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm" value={str("image_action") || "auto"} onChange={(e) => set("image_action", e.target.value === "auto" ? null : e.target.value)}>
              <option value="auto">auto</option>
              <option value="edit">edit</option>
              <option value="generate">generate</option>
            </select>
          </Field>
          <Field label="Image quality" hint="high is a good default for design work; xhigh/max only on gpt-image-2.5">
            <select className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm" value={str("image_quality") || "auto"} onChange={(e) => set("image_quality", e.target.value === "auto" ? null : e.target.value)}>
              {["auto", "low", "medium", "high", "xhigh", "max"].map((q) => <option key={q} value={q}>{q}</option>)}
            </select>
          </Field>
          <Field label="Output size" hint="Chosen from the request (16:9 → landscape, 4:5 → portrait, square …). Pin a size below only to override that."><p className="py-2 text-sm">From the requested ratio</p></Field>
          <Field label="Image input" hint="Attached images are sent to the model as input"><p className="py-2 text-sm">ON</p></Field>
          <Field label="Image generation" hint="Built-in image_generation tool; renders stream into the chat as they form">
            <label className="flex items-center gap-2 py-2 text-sm"><input type="checkbox" checked={imageGen} onChange={(e) => set("image_generation", e.target.checked ? null : false)} /> {imageGen ? "ON" : "OFF"}</label>
          </Field>
          <Field label="Pinned size (optional)" hint="e.g. 1792x1008 — overrides the ratio-based size for every request"><Input value={String((config.image_options as Record<string, unknown> | undefined)?.size ?? "")} placeholder="auto" onChange={(e) => { const opts = { ...((config.image_options as Record<string, unknown>) ?? {}) }; if (e.target.value) opts.size = e.target.value; else delete opts.size; set("image_options", Object.keys(opts).length ? opts : null); }} /></Field>

        </div>
      </Card>
      <Card>
        <CardTitle>Test Runtime</CardTitle>
        <p className="mb-2 text-xs text-muted">Runs the Origin-controlled runtime once with an optional image. Success means the actual generated image appears below — not a link, not &quot;completed&quot;. Nothing is written to a chat. Switch to Origin Native only after this looks right.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Prompt"><Input value={prompt} onChange={(e) => setPrompt(e.target.value)} /></Field>
          <Field label="Image (optional)"><input type="file" accept="image/*" className="block w-full text-xs text-muted" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></Field>
        </div>
        <div className="mt-3 flex items-center gap-2">
          <Button variant="secondary" disabled={busy !== null || !nativeReady} onClick={() => void runTest()}>{busy === "test" ? "Running…" : "Test Runtime"}</Button>
          {!nativeReady ? <span className="text-xs text-muted">Add a model and an API key first.</span> : null}
        </div>
        {testError ? <ErrorText>{testError}</ErrorText> : null}
        {result ? (
          <div className="mt-3 rounded-xl border border-border bg-surface p-3 text-sm">
            {result.ok ? (
              <>
                <p className="text-xs text-success">🟢 Completed in {(result.latency_ms / 1000).toFixed(1)}s{result.response_id ? ` · response ${result.response_id}` : ""}</p>
                {result.text ? <p className="mt-2 whitespace-pre-wrap">{result.text}</p> : null}
                {result.images.map((img) => (
                  <div key={img.filename} className="mt-2 max-w-md overflow-hidden rounded-lg border border-border">
                    {/* eslint-disable-next-line @next/next/no-img-element -- inline data URL from the test endpoint */}
                    <img src={img.data_url} alt={img.filename} className="block max-h-96 w-full object-contain bg-surface-2" />
                    <p className="px-2 py-1 text-[11px] text-faint">{img.filename}{img.revised_prompt ? ` · ${img.revised_prompt}` : ""}</p>
                  </div>
                ))}
                {!result.images.length && !result.text ? <p className="text-xs text-muted">The runtime answered without text or images.</p> : null}
              </>
            ) : (
              <p className="text-xs text-danger">🔴 {result.error_message} ({result.error_code})</p>
            )}
          </div>
        ) : null}
      </Card>
    </div>
  );
}

function TestTab({ agent, onTested }: { agent: AgentOut; onTested: () => Promise<void> }) {
  const [input, setInput] = useState("Hello! Please introduce yourself in one line.");
  const [result, setResult] = useState<AgentMessageTestOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const send = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await agentsApi.testMessage(agent.id, input));
      await onTested();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card>
      <CardTitle>Send a test message</CardTitle>
      <p className="mb-3 text-xs text-muted">Goes through exactly the same path as the chat, without creating a chat. Nothing is stored except the connection status.</p>
      <div className="flex gap-2">
        <Input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void send(); }} />
        <Button disabled={busy || !input.trim()} onClick={() => void send()}>{busy ? "Sending…" : "Send"}</Button>
      </div>
      <ErrorText>{error}</ErrorText>
      {result ? (
        <div className={`mt-3 rounded-lg border p-3 text-sm ${result.ok ? "border-success/40" : "border-danger/40"}`}>
          <p className="text-xs text-muted">{result.ok ? "🟢 Replied" : "🔴 Failed"} in {result.latency_ms} ms{result.session_native ? " · keeps its own session" : ""}{result.files_count ? ` · ${result.files_count} file(s)` : ""}{result.error_code ? ` · ${result.error_code}` : ""}</p>
          <p className="mt-1 whitespace-pre-wrap">{result.ok ? result.reply : result.error_message}</p>
        </div>
      ) : null}
    </Card>
  );
}

function ActivityTab({ agentId }: { agentId: string }) {
  const [rows, setRows] = useState<ActivityRunOut[] | null>(null);
  useEffect(() => {
    agentsApi.activity(agentId, 50).then(setRows).catch(() => setRows([]));
  }, [agentId]);
  return (
    <Card>
      <CardTitle action={<Link href={`/admin/activity?agent_id=${agentId}`} className="text-xs text-accent">Full log</Link>}>Recent messages</CardTitle>
      {rows === null ? <p className="text-sm text-muted">Loading…</p> : rows.length === 0 ? <EmptyState title="Not used yet" body="Messages sent to this agent from the chat will appear here." /> : (
        <ul className="divide-y divide-border text-sm">
          {rows.map((r) => (
            <li key={r.run_id} className="flex items-start gap-3 py-2">
              <RunBadge status={r.status} />
              <div className="min-w-0 flex-1">
                <Link href={`/c/${r.conversation_id}`} className="block truncate hover:underline">{r.user_input || r.conversation_title}</Link>
                {r.error_message ? <p className="truncate text-xs text-danger">{r.error_message}</p> : null}
              </div>
              <span className="shrink-0 text-xs text-faint">{r.duration_ms != null ? `${r.duration_ms} ms · ` : ""}{new Date(r.created_at).toLocaleString()}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function SettingsTab({ agent, mutate }: { agent: AgentOut; mutate: (fn: () => Promise<AgentOut>, msg: string) => Promise<void> }) {
  const router = useRouter();
  const [name, setName] = useState(agent.name);
  const [command, setCommand] = useState(agent.command);
  const [description, setDescription] = useState(agent.description);
  const [isDefault, setIsDefault] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    consoleApi.settings().then((s) => setIsDefault(s.default_agent_id === agent.id)).catch(() => setIsDefault(false));
  }, [agent.id]);
  const setDefault = async (on: boolean) => {
    try {
      await consoleApi.updateSettings({ default_agent_id: on ? agent.id : null });
      setIsDefault(on);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update");
    }
  };
  const remove = async () => {
    if (!window.confirm(`Delete ${agent.name}? This only works if it was never used in a chat.`)) return;
    try {
      await agentsApi.remove(agent.id);
      router.push("/admin/agents");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete");
    }
  };
  return (
    <div className="space-y-4">
      <Card>
        <CardTitle>Identity</CardTitle>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Command"><Input value={command} onChange={(e) => setCommand(e.target.value)} /></Field>
          <div className="sm:col-span-2"><Field label="Description"><Input value={description} onChange={(e) => setDescription(e.target.value)} /></Field></div>
        </div>
        <div className="mt-3"><Button onClick={() => void mutate(() => agentsApi.update(agent.id, { name, command, description }), "Saved")}>Save</Button></div>
      </Card>
      <Card>
        <CardTitle>Availability</CardTitle>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" checked={agent.status === "active"} onChange={(e) => void mutate(() => agentsApi.update(agent.id, { status: e.target.checked ? "active" : "disabled" }), e.target.checked ? "Enabled" : "Disabled")} /> Enabled — shown in the chat’s / menu</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={Boolean(isDefault)} disabled={isDefault === null} onChange={(e) => void setDefault(e.target.checked)} /> Default agent for plain messages</label>
        </div>
      </Card>
      <Card>
        <CardTitle>Danger zone</CardTitle>
        <p className="mb-2 text-xs text-muted">An agent that has already answered in a chat cannot be deleted (history keeps pointing at it); disable it instead.</p>
        <Button variant="danger" onClick={() => void remove()}>Delete agent</Button>
        <ErrorText>{error}</ErrorText>
      </Card>
    </div>
  );
}
