"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardTitle, EmptyState, ErrorText } from "@/components/ui/Card";
import { Field, Input, Textarea } from "@/components/ui/Input";
import { ApiError } from "@/lib/api/client";
import { commandsApi } from "@/lib/api/admin";
import { projectsApi } from "@/lib/api/workspaces";
import type { CommandOut } from "@/types/admin";
import type { ProjectOut, ProjectRuleOut } from "@/types/api";

export default function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<ProjectOut | null>(null);
  const [rules, setRules] = useState<ProjectRuleOut[]>([]);
  const [commands, setCommands] = useState<CommandOut[]>([]);
  const [summary, setSummary] = useState("");
  const [ruleName, setRuleName] = useState("");
  const [ruleText, setRuleText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const load = useCallback(
    () =>
      Promise.all([projectsApi.get(projectId), projectsApi.rules(projectId)])
        .then(([p, r]) => {
          setProject(p);
          setSummary(p.summary_text ?? "");
          setRules(r);
        })
        .catch((err: unknown) => {
          if (err instanceof ApiError && err.status === 404) setNotFound(true);
          else setError(err instanceof ApiError ? err.message : "Could not load project");
        }),
    [projectId],
  );

  useEffect(() => {
    void load();
    commandsApi.list().then(setCommands).catch(() => setCommands([]));
  }, [load]);

  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Request failed");
    }
  };

  if (notFound) return <><TopBar title="Project" /><main className="p-4"><EmptyState title="Project not found" /></main></>;
  if (!project) return <><TopBar title="Project" /><main className="p-4 text-sm text-muted">Loading…</main></>;
  const canEdit = project.my_role !== "viewer";

  return (
    <>
      <TopBar title={project.name} />
      <main className="grid flex-1 gap-4 p-4 lg:grid-cols-[1fr_340px]">
        <section className="space-y-4">
          <Card>
            <CardTitle action={<Link href={`/app/workspaces/${project.workspace_id}`} className="text-xs text-accent">← workspace</Link>}>
              Chat
            </CardTitle>
            <EmptyState
              title="Conversations arrive in Phase 3"
              body="This project will host a single chat where /master, /resize, /editable, /qc and other agents run with live execution status."
            />
            <div className="mt-3">
              <p className="mb-1 text-xs font-medium text-muted">Available commands (live from admin configuration)</p>
              {commands.length === 0 ? <p className="text-xs text-muted">No active agents yet.</p> : (
                <ul className="flex flex-wrap gap-2">
                  {commands.map((c) => (
                    <li key={c.agent_id} className="rounded-md border border-border px-2 py-1 text-xs" title={c.description}>
                      <span className="font-mono text-accent">{c.command}</span> {c.name}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>
          <Card>
            <CardTitle>Project summary</CardTitle>
            <p className="mb-2 text-xs text-muted">Concise snapshot supplied to every agent as project context.</p>
            <Textarea value={summary} onChange={(e) => setSummary(e.target.value)} disabled={!canEdit} />
            {canEdit ? <div className="mt-2"><Button onClick={() => void run(() => projectsApi.update(projectId, { summary_text: summary }))}>Save summary</Button></div> : null}
          </Card>
          <ErrorText>{error}</ErrorText>
        </section>
        <aside className="space-y-4">
          <Card>
            <CardTitle>Project rules</CardTitle>
            {rules.length === 0 ? <p className="text-xs text-muted">No rules yet.</p> : null}
            <ul className="space-y-2">
              {rules.map((r) => (
                <li key={r.id} className="rounded-md border border-border p-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">{r.name}</span>
                    <div className="flex items-center gap-2">
                      <Badge tone={r.is_active ? "success" : "neutral"}>{r.is_active ? "active" : "off"}</Badge>
                      {canEdit ? (
                        <button className="text-[11px] text-accent" onClick={() => void run(() => projectsApi.updateRule(projectId, r.id, { is_active: !r.is_active }))}>
                          toggle
                        </button>
                      ) : null}
                    </div>
                  </div>
                  <p className="mt-1 whitespace-pre-wrap text-xs text-muted">{r.rule_text}</p>
                </li>
              ))}
            </ul>
            {canEdit ? (
              <form
                className="mt-3 space-y-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  void run(async () => {
                    await projectsApi.createRule(projectId, { name: ruleName, rule_text: ruleText });
                    setRuleName("");
                    setRuleText("");
                  });
                }}
              >
                <Field label="Rule name"><Input required value={ruleName} onChange={(e) => setRuleName(e.target.value)} /></Field>
                <Field label="Rule"><Textarea required value={ruleText} onChange={(e) => setRuleText(e.target.value)} /></Field>
                <Button type="submit" variant="secondary" disabled={!ruleName.trim() || !ruleText.trim()}>Add rule</Button>
              </form>
            ) : null}
          </Card>
        </aside>
      </main>
    </>
  );
}
