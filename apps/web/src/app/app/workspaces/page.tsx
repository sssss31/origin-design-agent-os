"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardTitle, EmptyState, ErrorText } from "@/components/ui/Card";
import { Field, Input, Textarea } from "@/components/ui/Input";
import { ApiError } from "@/lib/api/client";
import { workspacesApi } from "@/lib/api/workspaces";
import { useSession } from "@/lib/session";
import type { WorkspaceOut } from "@/types/api";

export default function WorkspacesPage() {
  const session = useSession();
  const [items, setItems] = useState<WorkspaceOut[] | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => workspacesApi.list().then(setItems).catch(() => setItems([])), []);
  useEffect(() => {
    void load();
  }, [load, session.organizationId]);

  const canCreate = (session.me?.memberships ?? []).some(
    (m) => m.organization_id === session.organizationId && m.role !== "viewer",
  );

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await workspacesApi.create({ name, description: description || undefined, organization_id: session.organizationId ?? undefined });
      setName("");
      setDescription("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create workspace");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <TopBar title="Workspaces" />
      <main className="grid flex-1 gap-4 p-4 lg:grid-cols-[1fr_320px]">
        <section className="space-y-3">
          {items === null ? <p className="text-sm text-muted">Loading…</p> : null}
          {items?.length === 0 ? <EmptyState title="No workspaces yet" body="Create one to start organising projects, assets and chats." /> : null}
          {items?.map((ws) => (
            <Link key={ws.id} href={`/app/workspaces/${ws.id}`} className="block">
              <Card className="transition hover:border-accent">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-semibold">{ws.name}</p>
                    <p className="text-xs text-muted">{ws.description || ws.slug}</p>
                  </div>
                  <div className="flex gap-2">
                    <Badge tone="accent">{ws.my_role}</Badge>
                    {ws.status === "archived" ? <Badge tone="warning">archived</Badge> : null}
                  </div>
                </div>
              </Card>
            </Link>
          ))}
        </section>
        <aside>
          <Card>
            <CardTitle>New workspace</CardTitle>
            {canCreate ? (
              <form onSubmit={create} className="space-y-3">
                <Field label="Name">
                  <Input required maxLength={160} value={name} onChange={(e) => setName(e.target.value)} />
                </Field>
                <Field label="Description">
                  <Textarea value={description} onChange={(e) => setDescription(e.target.value)} />
                </Field>
                <ErrorText>{error}</ErrorText>
                <Button type="submit" disabled={busy || !name.trim()}>
                  Create
                </Button>
              </form>
            ) : (
              <p className="text-xs text-muted">Viewers cannot create workspaces.</p>
            )}
          </Card>
        </aside>
      </main>
    </>
  );
}
