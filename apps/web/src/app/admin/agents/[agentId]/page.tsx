"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { ConnectionForm, emptyDraft, type ConnectionDraft } from "@/components/admin/ConnectionForm";
import { ConnectionBadge, RunBadge, typeLabel } from "@/components/admin/StatusBadge";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardTitle, EmptyState, ErrorText } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Input";
import { Tabs } from "@/components/ui/Tabs";
import { agentsApi, consoleApi } from "@/lib/api/admin";
import type { ActivityRunOut, AgentMessageTestOut, AgentOut, ProviderConnectionOut } from "@/types/admin";

type Tab = "connection" | "test" | "activity" | "settings";
const TABS: { id: Tab; label: string }[] = [
  { id: "connection", label: "Connection" },
  { id: "test", label: "Test" },
  { id: "activity", label: "Activity" },
  { id: "settings", label: "Settings" },
];

export default function AgentDetailPage() {
  const { agentId } = useParams<{ agentId: string }>();
  const [agent, setAgent] = useState<AgentOut | null>(null);
  const [tab, setTab] = useState<Tab>("connection");
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
        <Badge tone={agent.status === "active" ? "success" : "neutral"}>{agent.status === "active" ? "enabled" : agent.status}</Badge>
        <span className="text-xs text-muted">{typeLabel(agent.connection?.connection_type)}{agent.connection?.api_endpoint ? ` · ${agent.connection.api_endpoint}` : ""}</span>
        {agent.connection?.connection_message && agent.connection.connection_status !== "unknown" ? <span className="text-xs text-faint">— {agent.connection.connection_message}</span> : null}
        <Link href={`/admin/agents/${agent.id}/advanced`} className="ml-auto text-xs text-muted hover:text-text">Advanced editor →</Link>
      </div>
      <Tabs tabs={TABS} value={tab} onChange={setTab} />
      {notice ? <p className="mt-2 text-xs text-success">{notice}</p> : null}
      <ErrorText>{error}</ErrorText>
      <div className="mt-3">
        {tab === "connection" ? <ConnectionTab key={agent.connection?.connection_tested_at ?? agent.id} agent={agent} isOrigin={isOrigin} mutate={mutate} /> : null}
        {tab === "test" ? <TestTab agent={agent} onTested={load} /> : null}
        {tab === "activity" ? <ActivityTab agentId={agent.id} /> : null}
        {tab === "settings" ? <SettingsTab agent={agent} mutate={mutate} /> : null}
      </div>
    </AdminShell>
  );
}

function ConnectionTab({ agent, isOrigin, mutate }: { agent: AgentOut; isOrigin: boolean; mutate: (fn: () => Promise<AgentOut>, msg: string) => Promise<void> }) {
  const [draft, setDraft] = useState<ConnectionDraft>(emptyDraft(agent.connection));
  const [test, setTest] = useState<ProviderConnectionOut | null>(null);
  const [busy, setBusy] = useState<"save" | "test" | null>(null);
  const save = async () => {
    setBusy("save");
    await mutate(() => agentsApi.setConnection(agent.id, { connection_type: draft.connection_type, api_endpoint: draft.api_endpoint || null, api_key: draft.api_key || undefined, config: draft.config }), "Connection saved");
    setDraft((d) => ({ ...d, api_key: "" }));
    setBusy(null);
  };
  const runTest = async () => {
    setBusy("test");
    try {
      if (draft.api_key || draft.api_endpoint !== (agent.connection?.api_endpoint ?? "")) await save();
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
        <Button disabled={busy !== null} onClick={() => void save()}>{busy === "save" ? "Saving…" : "Save"}</Button>
        <Button variant="secondary" disabled={busy !== null} onClick={() => void runTest()}>{busy === "test" ? "Testing…" : "Test connection"}</Button>
        {test ? <span className={`text-xs ${test.success ? "text-success" : "text-danger"}`}>{test.success ? "🟢" : "🔴"} {test.message} ({test.latency_ms} ms)</span> : null}
      </div>
    </Card>
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
