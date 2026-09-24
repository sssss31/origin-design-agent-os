"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { RunBadge } from "@/components/admin/StatusBadge";
import { Card, CardTitle, EmptyState } from "@/components/ui/Card";
import { consoleApi } from "@/lib/api/admin";
import type { OverviewOut } from "@/types/admin";

function Stat({ label, value, tone, href }: { label: string; value: string | number; tone?: "success" | "danger" | "warning"; href?: string }) {
  const color = tone === "success" ? "text-success" : tone === "danger" ? "text-danger" : tone === "warning" ? "text-warning" : "";
  const body = (
    <Card className="h-full">
      <p className="text-xs text-muted">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${color}`}>{value}</p>
    </Card>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}

/** Console overview: is everything connected, and is anything failing right now? */
export default function AdminOverview() {
  const [data, setData] = useState<OverviewOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    consoleApi.overview().then(setData).catch((e: Error) => setError(e.message));
  }, []);
  return (
    <AdminShell title="Overview">
      {error ? <p className="text-sm text-danger">{error}</p> : null}
      {!data ? <p className="text-sm text-muted">Loading…</p> : (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Agents" value={data.agents_total} href="/admin/agents" />
            <Stat label="Connected" value={data.agents_connected} tone="success" href="/admin/agents" />
            <Stat label="Failing" value={data.agents_failing} tone={data.agents_failing ? "danger" : undefined} href="/admin/agents" />
            <Stat label="Missing API key" value={data.agents_without_key} tone={data.agents_without_key ? "warning" : undefined} href="/admin/agents" />
            <Stat label="Messages (24 h)" value={data.runs_24h} href="/admin/activity" />
            <Stat label="Succeeded (24 h)" value={data.runs_24h_succeeded} tone="success" href="/admin/activity" />
            <Stat label="Failed (24 h)" value={data.runs_24h_failed} tone={data.runs_24h_failed ? "danger" : undefined} href="/admin/activity?status=failed" />
            <Stat label="Avg agent latency" value={data.avg_latency_ms_24h != null ? `${(data.avg_latency_ms_24h / 1000).toFixed(1)} s` : "—"} />
          </div>
          <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
            <Card>
              <CardTitle action={<Link href="/admin/activity?status=failed" className="text-xs text-accent">All failures</Link>}>Recent failures</CardTitle>
              {data.recent_failures.length === 0 ? <EmptyState title="No failed messages" body="Every agent call in the last runs completed." /> : (
                <ul className="divide-y divide-border text-sm">
                  {data.recent_failures.map((r) => (
                    <li key={r.run_id} className="flex items-start gap-3 py-2">
                      <RunBadge status={r.status} />
                      <div className="min-w-0 flex-1">
                        <p className="truncate"><span className="font-mono text-xs text-accent">{r.agent_command ?? "—"}</span> {r.user_input}</p>
                        <p className="truncate text-xs text-danger">{r.error_message ?? r.error_code ?? "failed"}</p>
                      </div>
                      <span className="shrink-0 text-xs text-faint">{new Date(r.created_at).toLocaleString()}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card>
              <CardTitle>Quick actions</CardTitle>
              <div className="space-y-1 text-sm">
                <Link href="/admin/agents/new" className="block rounded-md px-2 py-1.5 hover:bg-surface-2">＋ Add an agent</Link>
                <Link href="/admin/agents" className="block rounded-md px-2 py-1.5 hover:bg-surface-2">Connect API keys</Link>
                <Link href="/admin/settings" className="block rounded-md px-2 py-1.5 hover:bg-surface-2">Choose the default agent</Link>
                <Link href="/admin/users" className="block rounded-md px-2 py-1.5 hover:bg-surface-2">Invite users</Link>
                <Link href="/" className="block rounded-md px-2 py-1.5 text-muted hover:bg-surface-2">Open the chat</Link>
              </div>
            </Card>
          </div>
        </div>
      )}
    </AdminShell>
  );
}
