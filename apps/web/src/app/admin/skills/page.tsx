"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AdminShell, useAsyncAction } from "@/components/admin/AdminShell";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardTitle, EmptyState, ErrorText } from "@/components/ui/Card";
import { Field, Input, Textarea } from "@/components/ui/Input";
import { skillsApi } from "@/lib/api/admin";
import type { SkillOut } from "@/types/admin";

export default function SkillsPage() {
  const router = useRouter();
  const run = useAsyncAction();
  const [skills, setSkills] = useState<SkillOut[] | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    skillsApi.list().then(setSkills).catch(() => setSkills([]));
  }, []);
  return (
    <AdminShell title="Skills">
      <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
        <section className="space-y-3">
          {skills === null ? <p className="text-sm text-muted">Loading…</p> : null}
          {skills?.length === 0 ? <EmptyState title="No skills yet" body="Skills are reusable instruction packages shared across agents." /> : null}
          {skills?.map((s) => (
            <Link key={s.id} href={`/admin/skills/${s.id}`} className="block">
              <Card className="hover:border-accent">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold">{s.name} <span className="font-mono text-xs text-muted">{s.slug}</span></p>
                    <p className="truncate text-xs text-muted">{s.description || "—"}</p>
                  </div>
                  <div className="flex shrink-0 gap-2 text-xs">
                    {s.active_version ? <span className="text-muted">v{s.active_version.version}</span> : null}
                    {s.draft_version ? <Badge tone="warning">draft</Badge> : null}
                    <Badge>{s.scope}</Badge>
                    <Badge tone={s.status === "active" ? "success" : s.status === "draft" ? "warning" : "neutral"}>{s.status}</Badge>
                  </div>
                </div>
              </Card>
            </Link>
          ))}
        </section>
        <aside>
          <Card>
            <CardTitle>New skill</CardTitle>
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void run(async () => { const s = await skillsApi.create({ name, description, version: { instructions } }); router.push(`/admin/skills/${s.id}`); }, setError); }}>
              <Field label="Name"><Input required value={name} onChange={(e) => setName(e.target.value)} /></Field>
              <Field label="Description"><Input value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
              <Field label="Instructions"><Textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} /></Field>
              <ErrorText>{error}</ErrorText>
              <Button type="submit" disabled={!name.trim()}>Create draft</Button>
            </form>
          </Card>
        </aside>
      </div>
    </AdminShell>
  );
}
