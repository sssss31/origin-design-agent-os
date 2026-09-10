"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Card, CardTitle } from "@/components/ui/Card";
import { agentsApi, providersApi, skillsApi, toolsApi } from "@/lib/api/admin";

interface Counts {
  agents: number;
  activeAgents: number;
  skills: number;
  providers: number;
  healthyProviders: number;
  tools: number;
}

export default function AdminHome() {
  const [counts, setCounts] = useState<Counts | null>(null);
  useEffect(() => {
    Promise.all([agentsApi.list(), skillsApi.list(), providersApi.list(), toolsApi.list()])
      .then(([agents, skills, providers, tools]) =>
        setCounts({
          agents: agents.length,
          activeAgents: agents.filter((a) => a.status === "active").length,
          skills: skills.length,
          providers: providers.length,
          healthyProviders: providers.filter((p) => p.health_status === "ok").length,
          tools: tools.length,
        }),
      )
      .catch(() => setCounts(null));
  }, []);
  const tiles: [string, string, string][] = counts
    ? [
        ["Active agents", `${counts.activeAgents} / ${counts.agents}`, "/admin/agents"],
        ["Skills", String(counts.skills), "/admin/skills"],
        ["Providers healthy", `${counts.healthyProviders} / ${counts.providers}`, "/admin/providers"],
        ["Tools", String(counts.tools), "/admin/tools"],
      ]
    : [];
  return (
    <AdminShell title="Dashboard">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {tiles.map(([label, value, href]) => (
          <Link key={label} href={href}>
            <Card className="hover:border-accent">
              <p className="text-xs text-muted">{label}</p>
              <p className="mt-1 text-2xl font-semibold">{value}</p>
            </Card>
          </Link>
        ))}
      </div>
      <Card className="mt-4">
        <CardTitle>How changes take effect</CardTitle>
        <p className="text-xs text-muted">
          Agents and skills are versioned: editing creates a draft, <b>Publish</b> switches the active version, and older published versions can be re-activated (rollback). Providers, tools and bindings are read at run time, so nothing here needs a redeploy. Runs today and error rate arrive with the workflow runtime in Phase 5.
        </p>
      </Card>
    </AdminShell>
  );
}
