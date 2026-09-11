"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Card, CardTitle } from "@/components/ui/Card";
import { agentsApi, providersApi, skillsApi, toolsApi } from "@/lib/api/admin";
import { api } from "@/lib/api/client";
import { Button } from "@/components/ui/Button";

interface Usage {
  runs_today: number;
  runs_failed_today: number;
  error_rate: number;
  input_tokens_today: number;
  output_tokens_today: number;
  tool_calls_today: number;
  recent_errors: { run_id: string | null; code: string; message: string; created_at: string }[];
}

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
  const [usage, setUsage] = useState<Usage | null>(null);
  const [seedMsg, setSeedMsg] = useState<string | null>(null);
  useEffect(() => {
    api<Usage>("/admin/usage").then(setUsage).catch(() => setUsage(null));
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
        ["Runs today", usage ? `${usage.runs_today} (${usage.runs_failed_today} failed)` : "—", "/admin/audit"],
        ["Error rate", usage ? `${(usage.error_rate * 100).toFixed(1)}%` : "—", "/admin/audit"],
        ["Tokens today", usage ? `${usage.input_tokens_today + usage.output_tokens_today}` : "—", "/admin/audit"],
        ["Tool calls today", usage ? String(usage.tool_calls_today) : "—", "/admin/tools"],
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
        <CardTitle action={<Button variant="secondary" onClick={() => void api<{ agents: number; skills: number; tools: number; published: number }>("/admin/seed/design-agents", { method: "POST", body: { provider_type: "openai" } }).then((r) => setSeedMsg(`Seeded ${r.agents} agents, ${r.skills} skills, ${r.tools} tools (${r.published} published). Add the OpenAI key under Providers.`)).catch((e: Error) => setSeedMsg(e.message))}>Seed the eight design agents</Button>}>Design agents</CardTitle>
        <p className="text-xs text-muted">Creates /master, /resize, /editable, /qc, /copy, /asset, /export and /auto with their skills, tools and handoffs as editable rows. Safe to run again: existing entries are kept.</p>
        {seedMsg ? <p className="mt-2 text-xs text-success">{seedMsg}</p> : null}
        {usage?.recent_errors.length ? <ul className="mt-3 space-y-1 text-xs">{usage.recent_errors.slice(0, 5).map((e, i) => <li key={i} className="text-danger">{e.code}: {e.message}</li>)}</ul> : null}
      </Card>
      <Card className="mt-4">
        <CardTitle>How changes take effect</CardTitle>
        <p className="text-xs text-muted">
          Agents and skills are versioned: editing creates a draft, <b>Publish</b> switches the active version, and older published versions can be re-activated (rollback). Providers, tools and bindings are read at run time, so nothing here needs a redeploy. Runs today and error rate arrive with the workflow runtime in Phase 5.
        </p>
      </Card>
    </AdminShell>
  );
}
