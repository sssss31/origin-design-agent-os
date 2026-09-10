"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AdminShell, useAsyncAction } from "@/components/admin/AdminShell";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardTitle, EmptyState, ErrorText } from "@/components/ui/Card";
import { Field, Input, Textarea } from "@/components/ui/Input";
import { JsonField, Select } from "@/components/ui/JsonField";
import { Tabs } from "@/components/ui/Tabs";
import { agentsApi, providersApi, skillsApi, toolsApi } from "@/lib/api/admin";
import type { AgentOut, AgentSummaryOut, AgentTestOut, AgentVersionInput, AgentVersionOut, ProviderOut, SkillOut, ToolOut } from "@/types/admin";

type Tab = "general" | "instructions" | "skills" | "tools" | "model" | "connections" | "schemas" | "versions" | "test";
const TABS: { id: Tab; label: string }[] = [
  { id: "general", label: "General" },
  { id: "instructions", label: "Instructions" },
  { id: "skills", label: "Skills" },
  { id: "tools", label: "Tools" },
  { id: "model", label: "Model" },
  { id: "connections", label: "Connections" },
  { id: "schemas", label: "Schemas" },
  { id: "versions", label: "Versions" },
  { id: "test", label: "Test" },
];

export default function AgentEditorPage() {
  const { agentId } = useParams<{ agentId: string }>();
  const run = useAsyncAction();
  const [agent, setAgent] = useState<AgentOut | null>(null);
  const [tab, setTab] = useState<Tab>("general");
  const [providers, setProviders] = useState<ProviderOut[]>([]);
  const [skills, setSkills] = useState<SkillOut[]>([]);
  const [tools, setTools] = useState<ToolOut[]>([]);
  const [others, setOthers] = useState<AgentSummaryOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [publishNote, setPublishNote] = useState("");

  const load = useCallback(
    () =>
      Promise.all([agentsApi.get(agentId), providersApi.list(), skillsApi.list(), toolsApi.list(), agentsApi.list()])
        .then(([a, p, s, t, all]) => {
          setAgent(a);
          setProviders(p);
          setSkills(s);
          setTools(t);
          setOthers(all.filter((x) => x.id !== agentId));
        })
        .catch((err: unknown) => setError(err instanceof Error ? err.message : "Could not load agent")),
    [agentId],
  );
  useEffect(() => {
    void load();
  }, [load]);

  const mutate = (fn: () => Promise<AgentOut>, msg: string) => {
    setNotice(null);
    void run(async () => {
      setAgent(await fn());
      setNotice(msg);
    }, setError);
  };

  if (!agent) return <AdminShell title="Agent"><p className="text-sm text-muted">{error ?? "Loading…"}</p></AdminShell>;
  const working: AgentVersionOut | null = agent.draft_version ?? agent.active_version;
  const editingLabel = agent.draft_version ? `draft v${agent.draft_version.version}` : agent.active_version ? `v${agent.active_version.version} (published; editing creates a draft)` : "no version";

  return (
    <AdminShell title={`${agent.name} ${agent.command}`}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Badge tone={agent.status === "active" ? "success" : agent.status === "draft" ? "warning" : "neutral"}>{agent.status}</Badge>
        {agent.active_version ? <Badge tone="accent">active v{agent.active_version.version}</Badge> : null}
        <span className="text-xs text-muted">Editing: {editingLabel}</span>
        <div className="ml-auto flex items-center gap-2">
          <Input placeholder="Change note" value={publishNote} onChange={(e) => setPublishNote(e.target.value)} className="w-48" />
          <Button disabled={!agent.draft_version} onClick={() => mutate(() => agentsApi.publish(agent.id, { change_note: publishNote || undefined }), "Published")}>
            Publish draft
          </Button>
          {agent.status === "active" ? (
            <Button variant="secondary" onClick={() => mutate(() => agentsApi.update(agent.id, { status: "disabled" }), "Disabled")}>Disable</Button>
          ) : agent.active_version ? (
            <Button variant="secondary" onClick={() => mutate(() => agentsApi.update(agent.id, { status: "active" }), "Enabled")}>Enable</Button>
          ) : null}
        </div>
      </div>
      <Tabs tabs={TABS} value={tab} onChange={setTab} />
      <div className="mt-4">
        <ErrorText>{error}</ErrorText>
        {notice ? <p className="mb-2 text-xs text-success">{notice}</p> : null}
        {tab === "general" ? <GeneralTab agent={agent} onSave={(b) => mutate(() => agentsApi.update(agent.id, b), "Saved")} /> : null}
        {tab === "instructions" ? <InstructionsTab version={working} onSave={(b) => mutate(() => agentsApi.saveDraft(agent.id, b), "Draft saved")} /> : null}
        {tab === "skills" ? <SkillsTab agent={agent} version={working} skills={skills} mutate={mutate} /> : null}
        {tab === "tools" ? <ToolsTab agent={agent} version={working} tools={tools} mutate={mutate} /> : null}
        {tab === "model" ? <ModelTab version={working} providers={providers} onSave={(b) => mutate(() => agentsApi.saveDraft(agent.id, b), "Draft saved")} /> : null}
        {tab === "connections" ? <ConnectionsTab agent={agent} version={working} others={others} mutate={mutate} onSave={(b) => mutate(() => agentsApi.saveDraft(agent.id, b), "Draft saved")} /> : null}
        {tab === "schemas" ? <SchemasTab version={working} onSave={(b) => mutate(() => agentsApi.saveDraft(agent.id, b), "Draft saved")} /> : null}
        {tab === "versions" ? <VersionsTab agent={agent} mutate={mutate} /> : null}
        {tab === "test" ? <TestTab agent={agent} /> : null}
      </div>
    </AdminShell>
  );
}

function GeneralTab({ agent, onSave }: { agent: AgentOut; onSave: (b: Partial<Pick<AgentOut, "name" | "command" | "description" | "is_manager">>) => void }) {
  const [name, setName] = useState(agent.name);
  const [command, setCommand] = useState(agent.command);
  const [description, setDescription] = useState(agent.description);
  const [isManager, setIsManager] = useState(agent.is_manager);
  return (
    <Card className="max-w-2xl space-y-3">
      <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
      <Field label="Slug"><Input value={agent.slug} disabled /></Field>
      <Field label="Slash command"><Input value={command} onChange={(e) => setCommand(e.target.value)} /></Field>
      <Field label="Routing description" hint="Shown in the command menu and used by the Manager to route."><Textarea value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={isManager} onChange={(e) => setIsManager(e.target.checked)} /> Manager agent (handles /auto and plain messages)</label>
      <Button onClick={() => onSave({ name, command, description, is_manager: isManager })}>Save</Button>
    </Card>
  );
}

function InstructionsTab({ version, onSave }: { version: AgentVersionOut | null; onSave: (b: AgentVersionInput) => void }) {
  const [text, setText] = useState(version?.instructions ?? "");
  const [handoff, setHandoff] = useState(version?.handoff_description ?? "");
  const variables = ["{{workspace.name}}", "{{project.name}}", "{{brand.primary_color}}"];
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
      <Card className="space-y-3">
        <Field label="Primary system instructions"><Textarea rows={18} className="font-mono text-xs" value={text} onChange={(e) => setText(e.target.value)} /></Field>
        <Field label="Handoff description" hint="When the Manager should delegate to this agent."><Textarea value={handoff} onChange={(e) => setHandoff(e.target.value)} /></Field>
        <Button onClick={() => onSave({ instructions: text, handoff_description: handoff })}>Save draft</Button>
      </Card>
      <Card>
        <CardTitle>Composition preview</CardTitle>
        <ol className="list-decimal space-y-1 pl-4 text-xs text-muted">
          <li>Platform safety & runtime rules</li>
          <li>Organization global rules</li>
          <li><b className="text-text">These instructions</b> ({text.length} chars)</li>
          <li>Attached skills by priority</li>
          <li>Brand configuration + workspace rules</li>
          <li>Project rules + task context</li>
          <li>Current user request</li>
        </ol>
        <p className="mt-3 text-[11px] text-muted">Placeholders available in skills: {variables.join(", ")}</p>
      </Card>
    </div>
  );
}

function SkillsTab({ agent, version, skills, mutate }: { agent: AgentOut; version: AgentVersionOut | null; skills: SkillOut[]; mutate: (fn: () => Promise<AgentOut>, msg: string) => void }) {
  const [skillId, setSkillId] = useState("");
  const [priority, setPriority] = useState("100");
  const [pin, setPin] = useState(false);
  const attached = version?.skills ?? [];
  const available = skills.filter((s) => !attached.some((b) => b.skill_id === s.id));
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <Card>
        <CardTitle>Attached skills (lowest priority number first)</CardTitle>
        {attached.length === 0 ? <EmptyState title="No skills attached" /> : null}
        <ul className="divide-y divide-border">
          {attached.map((b) => (
            <li key={b.id} className="flex items-center justify-between py-2 text-sm">
              <span>
                {b.skill_name} <span className="font-mono text-xs text-muted">{b.skill_slug}</span>{" "}
                <Badge>{b.skill_version_id ? "pinned" : "follows active"}</Badge>
              </span>
              <span className="flex items-center gap-2">
                <Input className="w-20" type="number" defaultValue={b.priority} onBlur={(e) => mutate(() => agentsApi.attachSkill(agent.id, b.skill_id, { priority: Number(e.target.value), skill_version_id: b.skill_version_id, variables: b.variables }), "Priority updated")} aria-label="Priority" />
                <Button variant="ghost" onClick={() => mutate(() => agentsApi.detachSkill(agent.id, b.skill_id), "Skill detached")}>Detach</Button>
              </span>
            </li>
          ))}
        </ul>
      </Card>
      <Card className="space-y-3">
        <CardTitle>Attach skill</CardTitle>
        <Select label="Skill" value={skillId} onChange={setSkillId} options={[{ value: "", label: "Choose…" }, ...available.map((s) => ({ value: s.id, label: `${s.name} (${s.status})` }))]} />
        <Field label="Priority"><Input type="number" value={priority} onChange={(e) => setPriority(e.target.value)} /></Field>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={pin} onChange={(e) => setPin(e.target.checked)} /> Pin to the currently active skill version</label>
        <Button
          disabled={!skillId}
          onClick={() => {
            const skill = skills.find((s) => s.id === skillId);
            mutate(() => agentsApi.attachSkill(agent.id, skillId, { priority: Number(priority), skill_version_id: pin ? skill?.active_version_id ?? null : null }), "Skill attached to draft");
            setSkillId("");
          }}
        >
          Attach
        </Button>
      </Card>
    </div>
  );
}

function ToolsTab({ agent, version, tools, mutate }: { agent: AgentOut; version: AgentVersionOut | null; tools: ToolOut[]; mutate: (fn: () => Promise<AgentOut>, msg: string) => void }) {
  const bound = version?.tools ?? [];
  return (
    <Card>
      <CardTitle>Tool permissions for this agent</CardTitle>
      <p className="mb-3 text-xs text-muted">An agent can only call tools enabled here. Changes apply to the draft and take effect on publish.</p>
      {tools.length === 0 ? <EmptyState title="No tools defined" body="Create tools under Admin → Tools." /> : null}
      <ul className="divide-y divide-border">
        {tools.map((t) => {
          const b = bound.find((x) => x.tool_id === t.id);
          return (
            <li key={t.id} className="flex items-center justify-between py-2 text-sm">
              <span>
                {t.display_name} <span className="font-mono text-xs text-muted">{t.slug}</span> <Badge>{t.executor_type}</Badge>{" "}
                {t.status === "disabled" ? <Badge tone="danger">disabled</Badge> : null}
              </span>
              <span className="flex items-center gap-2">
                {b ? (
                  <>
                    <Input className="w-24" type="number" placeholder="max calls" defaultValue={b.max_calls_per_run ?? ""} onBlur={(e) => mutate(() => agentsApi.attachTool(agent.id, t.id, { max_calls_per_run: e.target.value ? Number(e.target.value) : null }), "Limit updated")} aria-label="Max calls per run" />
                    <Button variant="ghost" onClick={() => mutate(() => agentsApi.detachTool(agent.id, t.id), "Tool removed")}>Remove</Button>
                  </>
                ) : (
                  <Button variant="secondary" onClick={() => mutate(() => agentsApi.attachTool(agent.id, t.id, {}), "Tool enabled on draft")}>Enable</Button>
                )}
              </span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function ModelTab({ version, providers, onSave }: { version: AgentVersionOut | null; providers: ProviderOut[]; onSave: (b: AgentVersionInput) => void }) {
  const [providerId, setProviderId] = useState(version?.provider_id ?? "");
  const [model, setModel] = useState(version?.model ?? "");
  const [settings, setSettings] = useState<Record<string, unknown>>(version?.model_settings ?? {});
  const [maxSteps, setMaxSteps] = useState(String(version?.max_steps ?? 20));
  const [timeout, setTimeoutS] = useState(String(version?.timeout_seconds ?? 300));
  const [clarify, setClarify] = useState(version?.can_ask_clarification ?? true);
  const provider = providers.find((p) => p.id === providerId);
  const allowed = provider?.models.filter((m) => m.enabled) ?? [];
  return (
    <Card className="max-w-2xl space-y-3">
      <Select label="Provider" value={providerId} onChange={(v) => { setProviderId(v); setModel(providers.find((p) => p.id === v)?.default_model ?? ""); }} options={[{ value: "", label: "Choose…" }, ...providers.map((p) => ({ value: p.id, label: `${p.name} (${p.type}${p.enabled ? "" : ", disabled"})` }))]} />
      {allowed.length > 0 ? (
        <Select label="Model (allowlist)" value={model} onChange={setModel} options={[{ value: "", label: "Choose…" }, ...allowed.map((m) => ({ value: m.model, label: m.display_name ? `${m.display_name} — ${m.model}` : m.model }))]} />
      ) : (
        <Field label="Model" hint="This provider has no allowlist yet; any model id is accepted."><Input value={model} onChange={(e) => setModel(e.target.value)} /></Field>
      )}
      <JsonField label="Model settings (temperature, reasoning, …)" value={settings} onChange={setSettings} rows={4} />
      <div className="grid grid-cols-2 gap-3">
        <Field label="Max steps"><Input type="number" value={maxSteps} onChange={(e) => setMaxSteps(e.target.value)} /></Field>
        <Field label="Timeout (seconds)"><Input type="number" value={timeout} onChange={(e) => setTimeoutS(e.target.value)} /></Field>
      </div>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={clarify} onChange={(e) => setClarify(e.target.checked)} /> May pause the run to ask a blocking clarification question</label>
      <Button onClick={() => onSave({ provider_id: providerId || null, model: model || null, model_settings: settings, max_steps: Number(maxSteps), timeout_seconds: Number(timeout), can_ask_clarification: clarify })}>Save draft</Button>
    </Card>
  );
}

function ConnectionsTab({ agent, version, others, mutate, onSave }: { agent: AgentOut; version: AgentVersionOut | null; others: AgentSummaryOut[]; mutate: (fn: () => Promise<AgentOut>, msg: string) => void; onSave: (b: AgentVersionInput) => void }) {
  const [target, setTarget] = useState("");
  const [hint, setHint] = useState("");
  const [failure, setFailure] = useState(false);
  const [handoffDesc, setHandoffDesc] = useState(version?.handoff_description ?? "");
  const handoffs = version?.handoffs ?? [];
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <Card>
        <CardTitle>Allowed handoffs</CardTitle>
        {handoffs.length === 0 ? <EmptyState title="No handoffs" body="Without a handoff, this agent cannot delegate to another agent." /> : null}
        <ul className="divide-y divide-border">
          {handoffs.map((h) => (
            <li key={h.id} className="flex items-center justify-between py-2 text-sm">
              <span>
                {h.target_agent_name} <span className="font-mono text-xs text-accent">{h.target_agent_command}</span> {h.is_failure_route ? <Badge tone="danger">failure route</Badge> : null}
                <span className="block text-xs text-muted">{h.routing_hint}</span>
              </span>
              <Button variant="ghost" onClick={() => mutate(() => agentsApi.removeHandoff(agent.id, h.target_agent_id), "Handoff removed")}>Remove</Button>
            </li>
          ))}
        </ul>
        <div className="mt-4 space-y-2 border-t border-border pt-3">
          <Field label="Manager routing hint (handoff description)"><Textarea value={handoffDesc} onChange={(e) => setHandoffDesc(e.target.value)} /></Field>
          <Button variant="secondary" onClick={() => onSave({ handoff_description: handoffDesc })}>Save hint</Button>
        </div>
      </Card>
      <Card className="space-y-3">
        <CardTitle>Add handoff</CardTitle>
        <Select label="Target agent" value={target} onChange={setTarget} options={[{ value: "", label: "Choose…" }, ...others.map((o) => ({ value: o.id, label: `${o.name} ${o.command}` }))]} />
        <Field label="Routing hint"><Input value={hint} onChange={(e) => setHint(e.target.value)} /></Field>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={failure} onChange={(e) => setFailure(e.target.checked)} /> Failure route (e.g. QC fail → back to producer)</label>
        <Button disabled={!target} onClick={() => { mutate(() => agentsApi.addHandoff(agent.id, target, { routing_hint: hint, is_failure_route: failure }), "Handoff added to draft"); setTarget(""); setHint(""); }}>Add</Button>
      </Card>
    </div>
  );
}

function SchemasTab({ version, onSave }: { version: AgentVersionOut | null; onSave: (b: AgentVersionInput) => void }) {
  const [input, setInput] = useState<Record<string, unknown>>(version?.input_schema ?? {});
  const [output, setOutput] = useState<Record<string, unknown>>(version?.output_schema ?? {});
  return (
    <Card className="max-w-3xl space-y-3">
      <JsonField label="Requirement / input schema (JSON Schema)" value={input} onChange={setInput} rows={10} />
      <JsonField label="Structured output schema (JSON Schema)" value={output} onChange={setOutput} rows={10} />
      <Button onClick={() => onSave({ input_schema: input, output_schema: output })}>Save draft</Button>
    </Card>
  );
}

function VersionsTab({ agent, mutate }: { agent: AgentOut; mutate: (fn: () => Promise<AgentOut>, msg: string) => void }) {
  return (
    <Card>
      <CardTitle>Version history</CardTitle>
      <ul className="divide-y divide-border">
        {[...agent.versions].reverse().map((v) => (
          <li key={v.id} className="flex items-center justify-between py-2 text-sm">
            <span>
              v{v.version} {v.id === agent.active_version_id ? <Badge tone="success">active</Badge> : v.published_at ? <Badge>published</Badge> : <Badge tone="warning">draft</Badge>}
              <span className="block text-xs text-muted">
                {v.model ?? "no model"} · {v.skills.length} skills · {v.tools.length} tools · {v.handoffs.length} handoffs · {v.instructions.length} chars
                {v.change_note ? ` · ${v.change_note}` : ""} · {new Date(v.created_at).toLocaleString()}
              </span>
            </span>
            {v.published_at && v.id !== agent.active_version_id ? (
              <Button variant="secondary" onClick={() => mutate(() => agentsApi.publish(agent.id, { version_id: v.id }), `Rolled back to v${v.version}`)}>Make active</Button>
            ) : null}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function TestTab({ agent }: { agent: AgentOut }) {
  const run = useAsyncAction();
  const [input, setInput] = useState("");
  const [useDraft, setUseDraft] = useState(true);
  const [result, setResult] = useState<AgentTestOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="space-y-3">
        <CardTitle>Sandbox test</CardTitle>
        <Field label="Sample request"><Textarea value={input} onChange={(e) => setInput(e.target.value)} placeholder="/resize the approved poster to 4:5" /></Field>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={useDraft} onChange={(e) => setUseDraft(e.target.checked)} /> Use draft version when present</label>
        <ErrorText>{error}</ErrorText>
        <Button disabled={busy || !input.trim()} onClick={() => { setBusy(true); void run(() => agentsApi.test(agent.id, { input, use_draft: useDraft }), setError).then((r) => { if (r) setResult(r); setBusy(false); }); }}>
          {busy ? "Running…" : "Run test"}
        </Button>
      </Card>
      <Card>
        <CardTitle>Safe trace</CardTitle>
        {!result ? <p className="text-xs text-muted">Tools are not executed in the sandbox; calls are recorded. No hidden reasoning is shown.</p> : (
          <div className="space-y-2 text-xs">
            <p><b>v{result.version}</b> · {result.provider_type}/{result.model} via {result.runner} · {result.steps} steps · {result.duration_ms} ms</p>
            <p><b>Instruction sections:</b> {result.instruction_sections.join(" → ")} ({result.instruction_chars} chars)</p>
            <p><b>Tools available:</b> {result.tools.join(", ") || "none"}</p>
            {result.requires_clarification ? <p className="text-warning"><b>Clarification requested:</b> {result.question}</p> : null}
            <pre className="whitespace-pre-wrap rounded-md bg-surface-2 p-2">{result.output_text || "(no text output)"}</pre>
            {result.defaults_used.length ? <p><b>Defaults used:</b> {result.defaults_used.join("; ")}</p> : null}
          </div>
        )}
      </Card>
    </div>
  );
}
