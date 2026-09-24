"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { ConnectionForm, emptyDraft, type ConnectionDraft } from "@/components/admin/ConnectionForm";
import { Button } from "@/components/ui/Button";
import { Card, ErrorText } from "@/components/ui/Card";
import { Field, Input, Textarea } from "@/components/ui/Input";
import { agentsApi } from "@/lib/api/admin";
import type { AgentMessageTestOut, AgentOut } from "@/types/admin";

type Mode = "openai_responses" | "http" | "curl";

const MODES: { id: Mode; title: string; body: string }[] = [
  { id: "openai_responses", title: "OpenAI GPT agent", body: "An agent built on the OpenAI platform (prompt id + API key)." },
  { id: "http", title: "Custom HTTP endpoint", body: "Any service that answers a JSON POST with a reply." },
  { id: "curl", title: "Paste a cURL", body: "Have a working cURL from the agent's docs? Import it; Origin fills in the endpoint and key." },
];

/** The connection endpoint derives a connection from a pasted cURL: the first URL decides the type,
 * and the key is passed as-is (the server keeps only the Bearer token). */
function connectionFromCurl(curl: string): { connection_type: string; api_endpoint: string } {
  const url = /https?:\/\/[^\s'"\\]+/.exec(curl)?.[0] ?? "";
  if (/api\.openai\.com/.test(url)) return { connection_type: "openai_responses", api_endpoint: url.replace(/\/responses.*$/, "") || "https://api.openai.com/v1" };
  return { connection_type: "http", api_endpoint: url };
}

function slugify(name: string): string {
  return `/${name.toLowerCase().replace(/agent/g, "").replace(/[^a-z0-9]+/g, "").slice(0, 24) || "agent"}`;
}

/** Add-agent wizard: how it is called → identity + credentials → test & enable. */
export default function NewAgentPage() {
  const router = useRouter();
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [mode, setMode] = useState<Mode>("openai_responses");
  const [name, setName] = useState("");
  const [command, setCommand] = useState("");
  const [description, setDescription] = useState("");
  const [curl, setCurl] = useState("");
  const [draft, setDraft] = useState<ConnectionDraft>(emptyDraft());
  const [created, setCreated] = useState<AgentOut | null>(null);
  const [test, setTest] = useState<AgentMessageTestOut | null>(null);
  const [testInput, setTestInput] = useState("Hello! Please introduce yourself in one line.");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const chooseMode = (m: Mode) => {
    setMode(m);
    if (m !== "curl") setDraft({ ...emptyDraft(), connection_type: m, api_endpoint: m === "openai_responses" ? "https://api.openai.com/v1" : "" });
  };
  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      let agent = await agentsApi.create({ name, command, description });
      if (mode === "curl") {
        const derived = connectionFromCurl(curl);
        agent = await agentsApi.setConnection(agent.id, { ...derived, api_key: curl, config: {} });
      } else {
        agent = await agentsApi.setConnection(agent.id, { connection_type: draft.connection_type, api_endpoint: draft.api_endpoint || null, api_key: draft.api_key || undefined, config: draft.config });
      }
      setCreated(agent);
      setStep(3);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the agent");
    } finally {
      setBusy(false);
    }
  };
  const runTest = async () => {
    if (!created) return;
    setBusy(true);
    setError(null);
    try {
      setTest(await agentsApi.testMessage(created.id, testInput));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setBusy(false);
    }
  };
  const canContinue = name.trim() && /^\/[a-z0-9_-]+$/i.test(command) && (mode === "curl" ? curl.trim().length > 10 : draft.api_endpoint.trim().length > 0);

  return (
    <AdminShell title="Add agent">
      <div className="mx-auto max-w-2xl space-y-4">
        <ol className="flex items-center gap-2 text-xs text-muted">
          {["How it's called", "Details & key", "Test & enable"].map((label, i) => (
            <li key={label} className={`flex items-center gap-2 ${step === i + 1 ? "text-accent" : ""}`}>
              <span className={`flex h-5 w-5 items-center justify-center rounded-full border text-[11px] ${step > i + 1 ? "border-success bg-success text-white" : step === i + 1 ? "border-accent" : "border-border"}`}>{i + 1}</span>
              {label}
              {i < 2 ? <span className="mx-1 text-faint">›</span> : null}
            </li>
          ))}
        </ol>
        {step === 1 ? (
          <div className="grid gap-3 sm:grid-cols-3">
            {MODES.map((m) => (
              <button key={m.id} type="button" onClick={() => chooseMode(m.id)} className={`rounded-xl border p-4 text-left hover:border-accent ${mode === m.id ? "border-accent bg-accent-soft/40" : "border-border bg-surface"}`}>
                <p className="text-sm font-semibold">{m.title}</p>
                <p className="mt-1 text-xs text-muted">{m.body}</p>
              </button>
            ))}
            <div className="sm:col-span-3 flex justify-end"><Button onClick={() => setStep(2)}>Continue</Button></div>
          </div>
        ) : null}
        {step === 2 ? (
          <Card>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Name"><Input value={name} onChange={(e) => { setName(e.target.value); if (!command || command === slugify(name)) setCommand(slugify(e.target.value)); }} placeholder="Resize Agent" /></Field>
              <Field label="Command" hint="What users type in the chat"><Input value={command} onChange={(e) => setCommand(e.target.value.startsWith("/") ? e.target.value : `/${e.target.value}`)} placeholder="/resize" /></Field>
              <div className="sm:col-span-2"><Field label="Description" hint="Shown in the / menu"><Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Adapts the master design to new sizes" /></Field></div>
            </div>
            <div className="mt-4 border-t border-border pt-4">
              {mode === "curl" ? (
                <Field label="cURL from the agent's documentation" hint="The URL, headers and Bearer token are extracted; the key is stored encrypted and never shown again.">
                  <Textarea rows={7} value={curl} onChange={(e) => setCurl(e.target.value)} placeholder={"curl https://api.openai.com/v1/responses \\\n  -H 'Authorization: Bearer sk-…' \\\n  -d '{\"prompt\": {\"id\": \"pmpt_…\"}, \"input\": \"…\"}'"} className="font-mono text-xs" />
                </Field>
              ) : (
                <ConnectionForm draft={draft} onChange={setDraft} />
              )}
            </div>
            <ErrorText>{error}</ErrorText>
            <div className="mt-4 flex justify-between">
              <Button variant="secondary" onClick={() => setStep(1)}>Back</Button>
              <Button disabled={!canContinue || busy} onClick={() => void create()}>{busy ? "Creating…" : "Create & continue"}</Button>
            </div>
          </Card>
        ) : null}
        {step === 3 && created ? (
          <Card>
            <p className="text-sm"><span className="font-semibold">{created.name}</span> <span className="font-mono text-xs text-accent">{created.command}</span> is created{created.connection?.configured ? " with its API key" : ""}.</p>
            {created.connection?.api_endpoint ? <p className="mt-1 text-xs text-muted">Endpoint: {created.connection.api_endpoint}</p> : null}
            <div className="mt-4">
              <Field label="Send a test message"><Input value={testInput} onChange={(e) => setTestInput(e.target.value)} /></Field>
              <div className="mt-2 flex gap-2">
                <Button variant="secondary" disabled={busy} onClick={() => void runTest()}>{busy ? "Sending…" : "Send test"}</Button>
              </div>
              {test ? (
                <div className={`mt-3 rounded-lg border p-3 text-sm ${test.ok ? "border-success/40" : "border-danger/40"}`}>
                  <p className="text-xs text-muted">{test.ok ? "🟢 Replied" : "🔴 Failed"} in {test.latency_ms} ms{test.session_native ? " · keeps its own session" : ""}{test.files_count ? ` · ${test.files_count} file(s)` : ""}</p>
                  <p className="mt-1 whitespace-pre-wrap">{test.ok ? test.reply : test.error_message}</p>
                </div>
              ) : null}
            </div>
            <ErrorText>{error}</ErrorText>
            <div className="mt-4 flex justify-between">
              <Button variant="secondary" onClick={() => router.push(`/admin/agents/${created.id}`)}>Open agent</Button>
              <Button onClick={() => router.push("/admin/agents")}>Done</Button>
            </div>
          </Card>
        ) : null}
      </div>
    </AdminShell>
  );
}
