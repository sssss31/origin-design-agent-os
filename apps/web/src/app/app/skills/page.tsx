"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/shell/PageHeader";
import { Badge, Card } from "@/components/ui/Card";
import { skillsApi } from "@/lib/api/admin";
import { api } from "@/lib/api/client";
import { useSession } from "@/lib/session";
import type { SkillOut } from "@/types/admin";

const DEFAULT_SKILLS = [
  ["Brand & Asset Lock", "Preserve logos, key colors, hierarchy and approved assets."],
  ["Design Adaptation", "Aspect-ratio changes without uncontrolled cropping or distortion."],
  ["Editable SVG Rules", "Preserve vector/text structure and report unsupported reconstruction."],
  ["Design QC Checklist", "Content, typography, spacing, alignment, safe margins, brand checks."],
  ["Print Preflight", "Dimensions, bleed, DPI and file-format checks."],
  ["Artifact Naming", "Consistent names and version conventions."],
  ["Clarification Policy", "Ask only blocking questions; otherwise use safe defaults."],
  ["Manager Routing", "How to identify the specialist sequence and retry limits."],
];

export default function SkillsPage() {
  const session = useSession();
  const isAdmin = session.me?.capabilities.admin_console ?? false;
  const [skills, setSkills] = useState<SkillOut[] | null>(null);
  useEffect(() => {
    if (isAdmin) skillsApi.list().then(setSkills).catch(() => setSkills([]));
    else api<SkillOut[]>("/admin/skills").then(setSkills).catch(() => setSkills(null));
  }, [isAdmin]);
  return (
    <main className="flex-1 overflow-y-auto">
      <PageHeader title="Customize Skills" subtitle="Skills are reusable instruction packages attached to agents — brand rules, adaptation rules, QC checklists. Edit them once and every agent that uses them updates on publish." actions={isAdmin ? <Link href="/admin/skills" className="rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-accent-contrast">Open skill editor</Link> : null} />
      <div className="grid gap-3 px-8 pb-10 sm:grid-cols-2 xl:grid-cols-3">
        {skills ? skills.map((s) => (
          <Card key={s.id} className="flex flex-col">
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm font-semibold">{s.name}</p>
              <Badge tone={s.status === "active" ? "success" : s.status === "draft" ? "warning" : "neutral"}>{s.status}</Badge>
            </div>
            <p className="mt-1 flex-1 text-xs text-muted">{s.description || "—"}</p>
            <p className="mt-2 text-[11px] text-faint">{s.active_version ? `v${s.active_version.version} · ${s.active_version.instructions.length} chars` : "not published"}{s.draft_version ? " · draft pending" : ""}</p>
            {isAdmin ? <Link href={`/admin/skills/${s.id}`} className="mt-2 text-xs text-accent">Customize →</Link> : null}
          </Card>
        )) : DEFAULT_SKILLS.map(([name, desc]) => (
          <Card key={name} className="opacity-80">
            <p className="text-sm font-semibold">{name}</p>
            <p className="mt-1 text-xs text-muted">{desc}</p>
            <p className="mt-2 text-[11px] text-faint">Managed by your administrator</p>
          </Card>
        ))}
      </div>
    </main>
  );
}
