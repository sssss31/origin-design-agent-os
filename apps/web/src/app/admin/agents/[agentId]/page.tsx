"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AdminShell, useAsyncAction } from "@/components/admin/AdminShell";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardTitle, EmptyState, ErrorText } from "@/components/ui/Card";
import { Field, Input, Textarea } from "@/components/ui/Input";
import { JsonField, Select } from "@/components/ui/JsonField";
import { Tabs } from "@/components/ui/Tabs";
import Link from "next/link";
import { agentsApi, providersApi, skillsApi, toolsApi } from "@/lib/api/admin";
import type { AgentOut, AgentSummaryOut, AgentTestOut, AgentVersionInput, AgentVersionOut, ProviderOut, SkillOut, ToolOut } from "@/types/admin";

type Tab = "general" | "instructions" | "skills" | "tools" | "model" | "connections" | "schemas" | "versions" | "test";
const TABS: { id: Tab; label: string }[] = [
  { id: "general", label: "General" },
  { id: "instructions", label: "Instructions" },
  { id: "skills", label: "Skills" },
  { id: "tools", label: "Tools" },
  { id: "model", label: "AI Provider" },
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
        {tab === "model" ? <ModelTab agent={agent} version={working} providers={providers} onSave={(b) => mutate(() => agentsApi.saveDraft(agent.id, b), "Draft saved")} onSaveGeneral={(b) => mutate(() => agentsApi.update(agent.id, b), "Saved")} /> : null}
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
  const [pin, setPin] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [testInput, setTestInput] = useState("Create a premium healthcare poster");
  const [testResult, setTestResult] = useState<AgentTestOut | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const attached = [...(version?.skills ?? [])].sort((a, b) => a.priority - b.priority);
  const available = skills.filter((s) => !attached.some((b) => b.skill_id === s.id));
  const move = (index: number, dir: -1 | 1) => {
    const ids = attached.map((b) => b.skill_id);
    const j = index + dir;
    if (j < 0 || j >= ids.length) return;
    [ids[index], ids[j]] = [ids[j]!, ids[index]!];
    mutate(() => agentsApi.reorderSkills(agent.id, ids), "Order updated");
  };
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <Card>
        <CardTitle>Attached skills (composed in this order)</CardTitle>
        {attached.length === 0 ? <EmptyState title="No skills attached" body="Skills are reusable instruction packages: Design Analysis, Prompt Enhancement, Brand Guideline Analysis…" /> : null}
        <ul className="divide-y divide-border">
          {attached.map((b, i) => {
            const skill = skills.find((s) => s.id === b.skill_id);
            return (
              <li key={b.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                <span className="flex items-center gap-2">
                  <span className="flex flex-col">
                    <button aria-label="Move up" className="text-faint hover:text-text disabled:opacity-30" disabled={i === 0} onClick={() => move(i, -1)}>▲</button>
                    <button aria-label="Move down" className="text-faint hover:text-text disabled:opacity-30" disabled={i === attached.length - 1} onClick={() => move(i, 1)}>▼</button>
                  </span>
                  <span className={b.enabled ? "" : "text-muted line-through"}>
                    {b.skill_name} <span className="font-mono text-xs text-muted">{b.skill_slug}</span>{" "}
                    <Badge>{b.skill_version_id ? "pinned" : `v${skill?.active_version?.version ?? "?"} (follows active)`}</Badge>
                    {skill?.draft_version ? <Badge tone="warning">draft pending</Badge> : null}
                  </span>
                </span>
                <span className="flex items-center gap-1">
                  <Button variant="ghost" onClick={() => mutate(() => agentsApi.attachSkill(agent.id, b.skill_id, { priority: b.priority, skill_version_id: b.skill_version_id, variables: b.variables, enabled: !b.enabled }), b.enabled ? "Skill disabled" : "Skill enabled")}>{b.enabled ? "Disable" : "Enable"}</Button>
                  <Link href={`/admin/skills/${b.skill_id}`} className="rounded-md px-2 py-1 text-xs text-accent hover:bg-surface-2">Edit</Link>
                  <Button variant="ghost" onClick={() => { setTesting(b.skill_id); setTestResult(null); setTestError(null); }}>Test</Button>
                  <Button variant="ghost" onClick={() => mutate(() => agentsApi.detachSkill(agent.id, b.skill_id), "Skill removed")}>Remove</Button>
                </span>
              </li>
            );
          })}
        </ul>
        {testing ? (
          <div className="mt-3 space-y-2 rounded-md border border-border p-3">
            <p className="text-xs font-medium">Test “{skills.find((s) => s.id === testing)?.name}” with this agent (draft version of the skill if one exists)</p>
            <Textarea rows={2} value={testInput} onChange={(e) => setTestInput(e.target.value)} />
            <div className="flex gap-2">
              <Button onClick={() => { setTestError(null); skillsApi.test(testing, { agent_id: agent.id, input: testInput }).then(setTestResult).catch((err: unknown) => setTestError(err instanceof Error ? err.message : "Test failed")); }}>Run</Button>
              <Button variant="ghost" onClick={() => setTesting(null)}>Close</Button>
            </div>
            <ErrorText>{testError}</ErrorText>
            {testResult ? (
              <div className="text-xs">
                <p><b>Sections:</b> {testResult.instruction_sections.join(" → ")}</p>
                <pre className="mt-1 whitespace-pre-wrap rounded-md bg-surface-2 p-2">{testResult.output_text || "(no text)"}</pre>
              </div>
            ) : null}
          </div>
        ) : null}
      </Card>
      <Card className="space-y-3">
        <CardTitle>Add skill</CardTitle>
        <Select label="Skill" value={skillId} onChange={setSkillId} options={[{ value: "", label: "Choose…" }, ...available.map((s) => ({ value: s.id, label: `${s.name} (${s.status})` }))]} />
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={pin} onChange={(e) => setPin(e.target.checked)} /> Pin to the currently active skill version</label>
        <Button
          disabled={!skillId}
          onClick={() => {
            const skill = skills.find((s) => s.id === skillId);
            mutate(() => agentsApi.attachSkill(agent.id, skillId, { priority: (attached.length + 1) * 10, skill_version_id: pin ? skill?.active_version_id ?? null : null }), "Skill attached to draft");
            setSkillId("");
          }}
        >
          Add skill
        </Button>
        <p className="text-[11px] text-muted">Need a new one? <Link href="/admin/skills?new=1" className="text-accent">Create a skill</Link>. Skills are versioned independently; agents follow the active version unless pinned.</p>
      </Card>
    </div>
  );
}

function ToolsTab({ agent, version, tools, mutate }: { agent: AgentOut; version: AgentVersionOut | null; tools: ToolOut[]; mutate: (fn: () => Promise<AgentOut>, msg: string) => void }) {
  const bound = version?.tools ?? [];
  return (
    <Card>
      <CardTitle>Tools this agent may call</CardTitle>
      <p className="mb-3 text-xs text-muted">Agent → Skills → Tools → API Provider: an agent can only call tools bound here; each tool runs through its own executor (built-in function, custom REST API, MCP). Changes apply to the draft and take effect on publish.</p>
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
                    {!b.enabled ? <Badge tone="warning">disabled for this agent</Badge> : null}
                    <Input className="w-24" type="number" placeholder="max calls" defaultValue={b.max_calls_per_run ?? ""} onBlur={(e) => mutate(() => agentsApi.attachTool(agent.id, t.id, { max_calls_per_run: e.target.value ? Number(e.target.value) : null, enabled: b.enabled }), "Limit updated")} aria-label="Max calls per run" />
                    <Button variant="ghost" onClick={() => mutate(() => agentsApi.attachTool(agent.id, t.id, { max_calls_per_run: b.max_calls_per_run, enabled: !b.enabled }), b.enabled ? "Tool disabled" : "Tool enabled")}>{b.enabled ? "Disable" : "Enable"}</Button>
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

function ModelTab({ agent, version, providers, onSave, onSaveGeneral }: { agent: AgentOut; version: AgentVersionOut | null; providers: ProviderOut[]; onSave: (b: AgentVersionInput) => void; onSaveGeneral: (b: Partial<Pick<AgentOut, "name" | "command">>) => void }) {
  const [providerId, setProviderId] = useState(version?.provider_id ?? "");
  const [model, setModel] = useState(version?.model ?? "");
  const [name, setName] = useState(agent.name);
  const [command, setCommand] = useState(agent.command);
  const [instructions, setInstructions] = useState(version?.instructions ?? "");
  const settings = version?.model_settings ?? {};
  const [temperature, setTemperature] = useState(settings.temperature != null ? String(settings.temperature) : "");
  const [reasoning, setReasoning] = useState(typeof settings.reasoning_effort === "string" ? settings.reasoning_effort : typeof settings.reasoning === "object" && settings.reasoning ? String((settings.reasoning as { effort?: string }).effort ?? "") : "");
  const [maxOut, setMaxOut] = useState(settings.max_output_tokens != null ? String(settings.max_output_tokens) : "");
  const [maxSteps, setMaxSteps] = useState(String(version?.max_steps ?? 20));
  const [timeout, setTimeoutS] = useState(String(version?.timeout_seconds ?? 300));
  const [clarify, setClarify] = useState(version?.can_ask_clarification ?? true);
  const provider = providers.find((p) => p.id === providerId);
  const allowed = provider?.models.filter((m) => m.enabled && !m.resolved_capabilities.supports_image_generation) ?? [];
  const caps = provider?.models.find((m) => m.model === model)?.resolved_capabilities ?? {};
  const unconfigured = provider && provider.type !== "echo" && !provider.configured;
  const save = () => {
    const model_settings: Record<string, unknown> = {};
    if (caps.supports_temperature && temperature !== "") model_settings.temperature = Number(temperature);
    if (caps.supports_reasoning && reasoning) model_settings.reasoning_effort = reasoning;
    if (maxOut !== "") model_settings.max_output_tokens = Number(maxOut);
    onSave({ provider_id: providerId || null, model: model || null, instructions, model_settings, max_steps: Number(maxSteps), timeout_seconds: Number(timeout), can_ask_clarification: clarify });
    if (name !== agent.name || command !== agent.command) onSaveGeneral({ name, command });
  };
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
      <Card className="space-y-4">
        <div>
          <CardTitle>AI Provider</CardTitle>
          <div className="grid gap-3 sm:grid-cols-2">
            <Select label="Provider" value={providerId} onChange={(v) => { setProviderId(v); setModel(providers.find((p) => p.id === v)?.default_model ?? ""); }} options={[{ value: "", label: "Choose…" }, ...providers.map((p) => ({ value: p.id, label: `${p.name}${p.enabled ? "" : " (disabled)"}${p.type !== "echo" && !p.configured ? " — no key" : ""}` }))]} />
            {allowed.length > 0 ? (
              <Select label="Model" value={model} onChange={setModel} options={[{ value: "", label: "Choose…" }, ...allowed.map((m) => ({ value: m.model, label: m.display_name ? `${m.display_name} — ${m.model}` : m.model }))]} />
            ) : (
              <Field label="Model" hint={provider ? "No allowlist yet — set allowed models under API Integrations." : "Pick a provider first."}><Input value={model} onChange={(e) => setModel(e.target.value)} disabled={!provider} /></Field>
            )}
          </div>
          {unconfigured ? <p className="mt-2 text-xs text-warning">This provider has no API key. Add one under Admin → API Integrations before publishing.</p> : null}
          {caps.notes ? <p className="mt-2 text-[11px] text-muted">{caps.notes}</p> : null}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Agent command"><Input value={command} onChange={(e) => setCommand(e.target.value)} /></Field>
          <Field label="Agent name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
        </div>
        <Field label="System instructions"><Textarea rows={12} className="font-mono text-xs" value={instructions} onChange={(e) => setInstructions(e.target.value)} /></Field>
        <div className="grid gap-3 sm:grid-cols-3">
          {caps.supports_temperature ? <Field label="Temperature" hint="0 = deterministic, 2 = creative"><Input type="number" step="0.1" min={0} max={2} value={temperature} onChange={(e) => setTemperature(e.target.value)} placeholder="provider default" /></Field> : null}
          {caps.supports_reasoning ? (
            <Select label="Reasoning effort" value={reasoning} onChange={setReasoning} options={[{ value: "", label: "provider default" }, { value: "minimal", label: "minimal" }, { value: "low", label: "low" }, { value: "medium", label: "medium" }, { value: "high", label: "high" }]} />
          ) : null}
          <Field label="Max output tokens"><Input type="number" min={1} value={maxOut} onChange={(e) => setMaxOut(e.target.value)} placeholder={caps.max_output_tokens ? `up to ${caps.max_output_tokens}` : "provider default"} /></Field>
        </div>
        {model && !caps.supports_temperature && !caps.supports_reasoning ? <p className="text-[11px] text-muted">This model exposes no sampling controls; only max output tokens and tool settings are sent.</p> : null}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Max steps"><Input type="number" value={maxSteps} onChange={(e) => setMaxSteps(e.target.value)} /></Field>
          <Field label="Timeout (seconds)"><Input type="number" value={timeout} onChange={(e) => setTimeoutS(e.target.value)} /></Field>
        </div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={clarify} onChange={(e) => setClarify(e.target.checked)} /> May pause the run to ask a blocking clarification question</label>
        <Button onClick={save}>Save draft</Button>
      </Card>
      <Card>
        <CardTitle>Model capabilities</CardTitle>
        {model ? (
          <ul className="space-y-1 text-xs">
            {([["Temperature / top_p", caps.supports_temperature], ["Reasoning effort", caps.supports_reasoning], ["Vision input", caps.supports_vision], ["Tool calling", caps.supports_tools], ["Structured output", caps.supports_structured_output]] as const).map(([label, ok]) => (
              <li key={label} className="flex justify-between"><span className="text-muted">{label}</span><span>{ok ? "✓" : "—"}</span></li>
            ))}
            {caps.context_window ? <li className="flex justify-between"><span className="text-muted">Context window</span><span>{caps.context_window.toLocaleString()}</span></li> : null}
          </ul>
        ) : <p className="text-xs text-muted">Choose a model to see which parameters it accepts. Unsupported parameters are never sent to the provider.</p>}
        <p className="mt-3 text-[11px] text-muted">Every change here creates a new draft version; publish to make it live, or roll back from Versions.</p>
      </Card>
    </div>
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
  const [input, setInput] = useState("Create a premium healthcare poster");
  const [useDraft, setUseDraft] = useState(true);
  const [result, setResult] = useState<AgentTestOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const icon = { done: "✓", running: "●", failed: "✕", skipped: "–" } as const;
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
      <Card className="space-y-3">
        <CardTitle>Test Agent</CardTitle>
        <Field label="Request"><Textarea value={input} onChange={(e) => setInput(e.target.value)} placeholder="Create a premium healthcare poster" /></Field>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={useDraft} onChange={(e) => setUseDraft(e.target.checked)} /> Use draft version when present</label>
        <ErrorText>{error}</ErrorText>
        <Button disabled={busy || !input.trim()} onClick={() => { setBusy(true); setResult(null); void run(() => agentsApi.test(agent.id, { input, use_draft: useDraft }), setError).then((r) => { if (r) setResult(r); setBusy(false); }); }}>
          {busy ? "Running…" : "Run test"}
        </Button>
        <div className="rounded-md border border-border p-3">
          <p className="mb-2 text-xs font-medium">Execution</p>
          {!result && !busy ? <p className="text-xs text-muted">Provider → Agent → Skills → Context → Connection → Execution → Response → Usage. Tools are recorded, not executed.</p> : null}
          {busy ? <p className="text-xs text-muted">● Agent executing…</p> : null}
          {result ? (
            <ol className="space-y-1 text-xs">
              {result.steps.map((s, i) => (
                <li key={i} className={s.status === "failed" ? "text-danger" : s.status === "done" ? "text-success" : "text-muted"}>
                  {icon[s.status]} {s.label}{s.detail ? <span className="text-muted"> — {s.detail}</span> : null}
                </li>
              ))}
            </ol>
          ) : null}
        </div>
      </Card>
      <Card>
        <CardTitle>Result</CardTitle>
        {!result ? <p className="text-xs text-muted">Model, latency, tokens, estimated cost, tool calls and the response appear here. No hidden reasoning is shown.</p> : result.error_code ? (
          <div className="space-y-2 text-xs">
            <p className="text-danger"><b>{result.error_code}</b>: {result.error_message}</p>
            {result.error_code === "provider_secret_unavailable" ? <Link href="/admin/integrations" className="text-accent">Open API Integrations →</Link> : null}
          </div>
        ) : (
          <div className="space-y-2 text-xs">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3">
              <dt className="text-muted">Model</dt><dd className="font-mono">{result.model}</dd>
              <dt className="text-muted">Latency</dt><dd>{result.duration_ms} ms{result.usage.attempts > 1 ? ` (${result.usage.attempts} attempts)` : ""}</dd>
              <dt className="text-muted">Input tokens</dt><dd>{result.usage.input_tokens}{result.usage.cached_input_tokens ? ` (${result.usage.cached_input_tokens} cached)` : ""}</dd>
              <dt className="text-muted">Output tokens</dt><dd>{result.usage.output_tokens}{result.usage.reasoning_tokens ? ` (${result.usage.reasoning_tokens} reasoning)` : ""}</dd>
              <dt className="text-muted">Estimated cost</dt><dd>{result.usage.priced ? `$${result.usage.estimated_cost_usd.toFixed(5)}` : <Link href="/admin/usage" className="text-accent">no price configured</Link>}</dd>
              <dt className="text-muted">Tool calls</dt><dd>{result.usage.tool_calls}</dd>
            </dl>
            <p><b>Instruction sections:</b> {result.instruction_sections.join(" → ")} ({result.instruction_chars} chars)</p>
            <p><b>Tools available:</b> {result.tools.join(", ") || "none"}</p>
            {result.requires_clarification ? <p className="text-warning"><b>Clarification requested:</b> {result.question}</p> : null}
            <p className="font-medium">Response</p>
            <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-md bg-surface-2 p-2">{result.output_text || "(no text output)"}</pre>
            {result.defaults_used.length ? <p><b>Defaults used:</b> {result.defaults_used.join("; ")}</p> : null}
          </div>
        )}
      </Card>
    </div>
  );
}
