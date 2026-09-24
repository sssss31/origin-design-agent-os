"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { RunBadge } from "@/components/admin/StatusBadge";
import { Card, EmptyState } from "@/components/ui/Card";
import { Select } from "@/components/ui/JsonField";
import { agentsApi, consoleApi } from "@/lib/api/admin";
import type { ActivityRunOut, AgentSummaryOut } from "@/types/admin";

function ActivityView() {
  const params = useSearchParams();
  const [agent, setAgent] = useState(params.get("agent_id") ?? "");
  const [status, setStatus] = useState(params.get("status") ?? "");
  const [agents, setAgents] = useState<AgentSummaryOut[]>([]);
  const [rows, setRows] = useState<ActivityRunOut[] | null>(null);
  useEffect(() => {
    agentsApi.list().then(setAgents).catch(() => setAgents([]));
  }, []);
  useEffect(() => {
    consoleApi.activity({ agent_id: agent || undefined, status: status || undefined, limit: 100 }).then(setRows).catch(() => setRows([]));
  }, [agent, status]);
  return (
    <>
      <div className="mb-3 flex flex-wrap items-end gap-2">
        <div className="w-64"><Select label="Agent" value={agent} onChange={setAgent} options={[{ value: "", label: "All agents" }, ...agents.map((a) => ({ value: a.id, label: `${a.name} ${a.command}` }))]} /></div>
        <div className="w-44"><Select label="Status" value={status} onChange={setStatus} options={[{ value: "", label: "Any" }, { value: "succeeded", label: "Succeeded" }, { value: "failed", label: "Failed" }, { value: "running", label: "Running" }, { value: "cancelled", label: "Cancelled" }]} /></div>
        <span className="pb-2 text-xs text-muted">{rows?.length ?? 0} messages</span>
      </div>
      <Card>
        {rows === null ? <p className="text-sm text-muted">Loading…</p> : rows.length === 0 ? <EmptyState title="Nothing here" body="Messages sent to agents from the chat will be listed here with their status and errors." /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted">
                <tr><th className="py-1 pr-3 font-medium">When</th><th className="py-1 pr-3 font-medium">Agent</th><th className="py-1 pr-3 font-medium">Message</th><th className="py-1 pr-3 font-medium">Status</th><th className="py-1 pr-3 font-medium">Time</th><th className="py-1 font-medium">Error</th></tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rows.map((r) => (
                  <tr key={r.run_id}>
                    <td className="whitespace-nowrap py-1.5 pr-3 text-xs text-faint">{new Date(r.created_at).toLocaleString()}</td>
                    <td className="py-1.5 pr-3 text-xs">{r.agent_name ?? "—"} <span className="font-mono text-accent">{r.agent_command ?? ""}</span></td>
                    <td className="max-w-[360px] truncate py-1.5 pr-3"><Link href={`/c/${r.conversation_id}`} className="hover:underline">{r.user_input || r.conversation_title}</Link></td>
                    <td className="py-1.5 pr-3"><RunBadge status={r.status} /></td>
                    <td className="whitespace-nowrap py-1.5 pr-3 text-xs text-muted">{r.duration_ms != null ? `${r.duration_ms} ms` : "—"}</td>
                    <td className="max-w-[260px] truncate py-1.5 text-xs text-danger">{r.error_message ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

export default function ActivityPage() {
  return (
    <AdminShell title="Activity">
      <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
        <ActivityView />
      </Suspense>
    </AdminShell>
  );
}
