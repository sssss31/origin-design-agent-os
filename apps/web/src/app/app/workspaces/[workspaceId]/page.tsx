"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardTitle, EmptyState, ErrorText } from "@/components/ui/Card";
import { Field, Input, Textarea } from "@/components/ui/Input";
import { ApiError } from "@/lib/api/client";
import { workspacesApi } from "@/lib/api/workspaces";
import type { ProjectOut, WorkspaceMemberOut, WorkspaceOut } from "@/types/api";

export default function WorkspacePage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const [ws, setWs] = useState<WorkspaceOut | null>(null);
  const [projects, setProjects] = useState<ProjectOut[]>([]);
  const [members, setMembers] = useState<WorkspaceMemberOut[]>([]);
  const [notFound, setNotFound] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [rules, setRules] = useState("");
  const [memberEmail, setMemberEmail] = useState("");
  const [memberRole, setMemberRole] = useState("member");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  const load = useCallback(
    () =>
      Promise.all([workspacesApi.get(workspaceId), workspacesApi.projects(workspaceId), workspacesApi.members(workspaceId)])
        .then(([w, p, m]) => {
          setWs(w);
          setRules(w.rules_text ?? "");
          setProjects(p);
          setMembers(m);
        })
        .catch((err: unknown) => {
          if (err instanceof ApiError && err.status === 404) setNotFound(true);
          else setError(err instanceof ApiError ? err.message : "Could not load workspace");
        }),
    [workspaceId],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const run = async (fn: () => Promise<unknown>, okMessage: string) => {
    setError(null);
    setSaved(null);
    try {
      await fn();
      setSaved(okMessage);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Request failed");
    }
  };

  if (notFound) {
    return (
      <>
        <TopBar title="Workspace" />
        <main className="p-4"><EmptyState title="Workspace not found" body="It may not exist or you may not have access." /></main>
      </>
    );
  }
  if (!ws) return <><TopBar title="Workspace" /><main className="p-4 text-sm text-muted">Loading…</main></>;

  const isAdmin = ws.my_role === "admin";
  const canEdit = ws.my_role !== "viewer";

  return (
    <>
      <TopBar title={ws.name} />
      <main className="grid flex-1 gap-4 p-4 lg:grid-cols-[1fr_340px]">
        <section className="space-y-4">
          <Card>
            <CardTitle action={<Badge tone="accent">{ws.my_role}</Badge>}>Projects</CardTitle>
            {projects.length === 0 ? <EmptyState title="No projects yet" /> : null}
            <ul className="divide-y divide-border">
              {projects.map((p) => (
                <li key={p.id} className="flex items-center justify-between py-2">
                  <Link href={`/app/projects/${p.id}`} className="text-sm font-medium hover:text-accent">
                    {p.name}
                  </Link>
                  <span className="text-xs text-muted">{new Date(p.created_at).toLocaleDateString()}</span>
                </li>
              ))}
            </ul>
            {canEdit ? (
              <form
                className="mt-3 flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  void run(async () => {
                    await workspacesApi.createProject(workspaceId, { name: projectName });
                    setProjectName("");
                  }, "Project created");
                }}
              >
                <Input placeholder="New project name" required value={projectName} onChange={(e) => setProjectName(e.target.value)} />
                <Button type="submit" disabled={!projectName.trim()}>Add</Button>
              </form>
            ) : null}
          </Card>
          <Card>
            <CardTitle>Workspace rules</CardTitle>
            <p className="mb-2 text-xs text-muted">Injected into every agent prompt for this workspace (after organization rules, before project rules).</p>
            <Textarea value={rules} onChange={(e) => setRules(e.target.value)} disabled={!isAdmin} />
            {isAdmin ? (
              <div className="mt-2">
                <Button onClick={() => void run(() => workspacesApi.update(workspaceId, { rules_text: rules }), "Rules saved")}>Save rules</Button>
              </div>
            ) : null}
          </Card>
          <ErrorText>{error}</ErrorText>
          {saved ? <p className="text-xs text-success">{saved}</p> : null}
        </section>
        <aside className="space-y-4">
          <Card>
            <CardTitle>Members</CardTitle>
            <ul className="space-y-1">
              {members.map((m) => (
                <li key={m.user_id} className="flex items-center justify-between text-sm">
                  <span>{m.display_name} <span className="text-xs text-muted">{m.email}</span></span>
                  <Badge>{m.role}</Badge>
                </li>
              ))}
            </ul>
            {isAdmin ? (
              <form
                className="mt-3 space-y-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  void run(async () => {
                    await workspacesApi.addMember(workspaceId, memberEmail, memberRole);
                    setMemberEmail("");
                  }, "Member updated");
                }}
              >
                <Field label="Add member by email">
                  <Input type="email" required value={memberEmail} onChange={(e) => setMemberEmail(e.target.value)} />
                </Field>
                <div className="flex gap-2">
                  <select className="rounded-md border border-border bg-surface px-2 text-xs" value={memberRole} onChange={(e) => setMemberRole(e.target.value)} aria-label="Role">
                    <option value="admin">admin</option>
                    <option value="member">member</option>
                    <option value="viewer">viewer</option>
                  </select>
                  <Button type="submit" variant="secondary">Add</Button>
                </div>
              </form>
            ) : null}
          </Card>
          <Card>
            <CardTitle>Details</CardTitle>
            <dl className="space-y-1 text-xs">
              <div className="flex justify-between"><dt className="text-muted">Slug</dt><dd>{ws.slug}</dd></div>
              <div className="flex justify-between"><dt className="text-muted">Status</dt><dd>{ws.status}</dd></div>
              <div className="flex justify-between"><dt className="text-muted">Created</dt><dd>{new Date(ws.created_at).toLocaleString()}</dd></div>
            </dl>
          </Card>
        </aside>
      </main>
    </>
  );
}
