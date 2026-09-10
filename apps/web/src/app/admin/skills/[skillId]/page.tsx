"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AdminShell, useAsyncAction } from "@/components/admin/AdminShell";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardTitle, ErrorText } from "@/components/ui/Card";
import { Field, Input, Textarea } from "@/components/ui/Input";
import { JsonField, Select } from "@/components/ui/JsonField";
import { Tabs } from "@/components/ui/Tabs";
import { skillsApi, toolsApi } from "@/lib/api/admin";
import type { SkillOut, SkillVersionInput, SkillVersionOut, ToolOut } from "@/types/admin";

type Tab = "instructions" | "variables" | "tools" | "files" | "versions";

export default function SkillEditorPage() {
  const { skillId } = useParams<{ skillId: string }>();
  const run = useAsyncAction();
  const [skill, setSkill] = useState<SkillOut | null>(null);
  const [tools, setTools] = useState<ToolOut[]>([]);
  const [tab, setTab] = useState<Tab>("instructions");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const load = useCallback(
    () => Promise.all([skillsApi.get(skillId), toolsApi.list()]).then(([s, t]) => { setSkill(s); setTools(t); }).catch((err: unknown) => setError(err instanceof Error ? err.message : "Could not load skill")),
    [skillId],
  );
  useEffect(() => { void load(); }, [load]);
  const mutate = (fn: () => Promise<SkillOut>, msg: string) => { setNotice(null); void run(async () => { setSkill(await fn()); setNotice(msg); }, setError); };
  if (!skill) return <AdminShell title="Skill"><p className="text-sm text-muted">{error ?? "Loading…"}</p></AdminShell>;
  const working: SkillVersionOut | null = skill.draft_version ?? skill.active_version;
  const save = (b: SkillVersionInput) => mutate(() => skillsApi.saveDraft(skill.id, b), "Draft saved");
  return (
    <AdminShell title={skill.name}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Badge tone={skill.status === "active" ? "success" : skill.status === "draft" ? "warning" : "neutral"}>{skill.status}</Badge>
        {skill.active_version ? <Badge tone="accent">active v{skill.active_version.version}</Badge> : null}
        <span className="text-xs text-muted">Editing: {skill.draft_version ? `draft v${skill.draft_version.version}` : skill.active_version ? `v${skill.active_version.version} (editing creates a draft)` : "no version"}</span>
        <div className="ml-auto flex gap-2">
          <Button disabled={!skill.draft_version} onClick={() => mutate(() => skillsApi.publish(skill.id), "Published")}>Publish draft</Button>
          {skill.status === "active" ? <Button variant="secondary" onClick={() => mutate(() => skillsApi.update(skill.id, { status: "disabled" }), "Disabled")}>Disable</Button> : skill.active_version ? <Button variant="secondary" onClick={() => mutate(() => skillsApi.update(skill.id, { status: "active" }), "Enabled")}>Enable</Button> : null}
        </div>
      </div>
      <Tabs tabs={[{ id: "instructions", label: "Instructions" }, { id: "variables", label: "Variables" }, { id: "tools", label: "Required tools" }, { id: "files", label: "Knowledge files" }, { id: "versions", label: "Versions" }]} value={tab} onChange={setTab} />
      <div className="mt-4 space-y-2">
        <ErrorText>{error}</ErrorText>
        {notice ? <p className="text-xs text-success">{notice}</p> : null}
        {tab === "instructions" ? <InstructionsTab skill={skill} version={working} save={save} onMeta={(b) => mutate(() => skillsApi.update(skill.id, b), "Saved")} /> : null}
        {tab === "variables" ? <VariablesTab version={working} save={save} /> : null}
        {tab === "tools" ? <ToolsTab version={working} tools={tools} save={save} /> : null}
        {tab === "files" ? <FilesTab skill={skill} version={working} mutate={mutate} /> : null}
        {tab === "versions" ? <VersionsTab skill={skill} mutate={mutate} /> : null}
      </div>
    </AdminShell>
  );
}

function InstructionsTab({ skill, version, save, onMeta }: { skill: SkillOut; version: SkillVersionOut | null; save: (b: SkillVersionInput) => void; onMeta: (b: { name?: string; description?: string; scope?: SkillOut["scope"] }) => void }) {
  const [name, setName] = useState(skill.name);
  const [description, setDescription] = useState(skill.description);
  const [scope, setScope] = useState(skill.scope);
  const [text, setText] = useState(version?.instructions ?? "");
  const [priority, setPriority] = useState(String(version?.default_priority ?? 100));
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
      <Card className="space-y-3">
        <Field label="Instructions (markdown; use {{variable}} placeholders)"><Textarea rows={16} className="font-mono text-xs" value={text} onChange={(e) => setText(e.target.value)} /></Field>
        <Field label="Default priority (lower runs earlier in the prompt)"><Input type="number" value={priority} onChange={(e) => setPriority(e.target.value)} /></Field>
        <Button onClick={() => save({ instructions: text, default_priority: Number(priority) })}>Save draft</Button>
      </Card>
      <Card className="space-y-3">
        <CardTitle>Metadata</CardTitle>
        <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Description"><Textarea value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        <Select label="Scope" value={scope} onChange={(v) => setScope(v as SkillOut["scope"])} options={[{ value: "global", label: "global" }, { value: "organization", label: "organization" }, { value: "workspace", label: "workspace" }]} />
        <Button variant="secondary" onClick={() => onMeta({ name, description, scope })}>Save metadata</Button>
      </Card>
    </div>
  );
}

function VariablesTab({ version, save }: { version: SkillVersionOut | null; save: (b: SkillVersionInput) => void }) {
  const [schema, setSchema] = useState<Record<string, unknown>>(version?.variables_schema ?? {});
  const [defaults, setDefaults] = useState<Record<string, unknown>>(version?.variables_defaults ?? {});
  return (
    <Card className="max-w-3xl space-y-3">
      <JsonField label="Variables schema (JSON Schema)" value={schema} onChange={setSchema} rows={8} />
      <JsonField label="Default values" value={defaults} onChange={setDefaults} rows={5} />
      <p className="text-xs text-muted">Agents may override defaults per binding. Unknown placeholders stay visible in the prompt so they are easy to spot.</p>
      <Button onClick={() => save({ variables_schema: schema, variables_defaults: defaults })}>Save draft</Button>
    </Card>
  );
}

function ToolsTab({ version, tools, save }: { version: SkillVersionOut | null; tools: ToolOut[]; save: (b: SkillVersionInput) => void }) {
  const [selected, setSelected] = useState<string[]>(version?.tool_requirements ?? []);
  return (
    <Card className="max-w-2xl space-y-3">
      <CardTitle>Tools that must be available when this skill is attached</CardTitle>
      {tools.map((t) => (
        <label key={t.id} className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={selected.includes(t.slug)} onChange={(e) => setSelected(e.target.checked ? [...selected, t.slug] : selected.filter((s) => s !== t.slug))} />
          {t.display_name} <span className="font-mono text-xs text-muted">{t.slug}</span>
        </label>
      ))}
      <Button onClick={() => save({ tool_requirements: selected })}>Save draft</Button>
    </Card>
  );
}

function FilesTab({ skill, version, mutate }: { skill: SkillOut; version: SkillVersionOut | null; mutate: (fn: () => Promise<SkillOut>, msg: string) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [description, setDescription] = useState("");
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <Card>
        <CardTitle>Knowledge / reference files ({version ? `v${version.version}` : "—"})</CardTitle>
        {version?.files.length ? (
          <ul className="divide-y divide-border text-sm">
            {version.files.map((f) => (
              <li key={f.id} className="flex justify-between py-2"><span>{f.filename} <span className="text-xs text-muted">{f.mime_type} · {f.size_bytes} B</span></span><span className="text-xs text-muted">{f.description}</span></li>
            ))}
          </ul>
        ) : <p className="text-xs text-muted">No files attached.</p>}
      </Card>
      <Card className="space-y-3">
        <CardTitle>Upload</CardTitle>
        <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-xs" aria-label="Knowledge file" />
        <Field label="Description"><Input value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        <Button disabled={!file} onClick={() => { if (file) mutate(() => skillsApi.uploadFile(skill.id, file, description || undefined), "File added to draft"); }}>Upload to draft</Button>
      </Card>
    </div>
  );
}

function VersionsTab({ skill, mutate }: { skill: SkillOut; mutate: (fn: () => Promise<SkillOut>, msg: string) => void }) {
  return (
    <Card>
      <ul className="divide-y divide-border">
        {[...skill.versions].reverse().map((v) => (
          <li key={v.id} className="flex items-center justify-between py-2 text-sm">
            <span>
              v{v.version} {v.id === skill.active_version_id ? <Badge tone="success">active</Badge> : v.published_at ? <Badge>published</Badge> : <Badge tone="warning">draft</Badge>}
              <span className="block text-xs text-muted">{v.instructions.length} chars · {v.files.length} files · {v.tool_requirements.length} tools{v.change_note ? ` · ${v.change_note}` : ""} · {new Date(v.created_at).toLocaleString()}</span>
            </span>
            {v.published_at && v.id !== skill.active_version_id ? <Button variant="secondary" onClick={() => mutate(() => skillsApi.publish(skill.id, { version_id: v.id }), `Rolled back to v${v.version}`)}>Make active</Button> : null}
          </li>
        ))}
      </ul>
    </Card>
  );
}
