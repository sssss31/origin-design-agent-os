"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AdminShell, useAsyncAction } from "@/components/admin/AdminShell";
import { ConnectionBadge, typeLabel } from "@/components/admin/StatusBadge";
import { Button } from "@/components/ui/Button";
import { Badge, Card, EmptyState, ErrorText } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { agentsApi, consoleApi } from "@/lib/api/admin";
import type { AgentSummaryOut } from "@/types/admin";

export default function AgentsPage() {
  const router = useRouter();
  const run = useAsyncAction();
  const [agents, setAgents] = useState<AgentSummaryOut[] | null>(null);
  const [defaultAgent, setDefaultAgent] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => agentsApi.list().then((list) => setAgents(list.filter((a) => !a.is_manager))).catch(() => setAgents([])), []);
  useEffect(() => {
    void load();
    consoleApi.settings().then((s) => setDefaultAgent(s.default_agent_id)).catch(() => undefined);
  }, [load]);
  const visible = (agents ?? []).filter((a) => (a.name + a.command).toLowerCase().includes(search.toLowerCase()));
  return (
    <AdminShell title="Agents">
      <div className="mb-3 flex items-center gap-2">
        <div className="w-72"><Input placeholder="Search name or /command" value={search} onChange={(e) => setSearch(e.target.value)} /></div>
        <span className="text-xs text-muted">{visible.length} agents</span>
        <Button className="ml-auto" onClick={() => router.push("/admin/agents/new")}><Plus size={14} /> Add agent</Button>
      </div>
      <ErrorText>{error}</ErrorText>
      {agents === null ? <p className="text-sm text-muted">Loading…</p> : null}
      {agents?.length === 0 ? (
        <Card>
          <EmptyState title="No agents yet" body="Add your first agent, or create the eight standard commands and fill in their endpoints and keys." />
          <div className="mt-3 flex justify-center gap-2">
            <Button onClick={() => router.push("/admin/agents/new")}>Add agent</Button>
            <Button variant="secondary" onClick={() => void run(() => agentsApi.seedRegistry("openai_responses").then(load), setError)}>Create the 8 standard commands</Button>
          </div>
        </Card>
      ) : null}
      {visible.length ? (
        <div className="overflow-x-auto rounded-xl border border-border bg-surface">
          <table className="w-full text-sm">
            <thead className="bg-surface-2 text-left text-xs text-muted">
              <tr>
                <th className="px-3 py-2 font-medium">Agent</th>
                <th className="px-3 py-2 font-medium">Type</th>
                <th className="px-3 py-2 font-medium">Endpoint</th>
                <th className="px-3 py-2 font-medium">API key</th>
                <th className="px-3 py-2 font-medium">Connection</th>
                <th className="px-3 py-2 font-medium">Enabled</th>
                <th className="px-3 py-2 font-medium">Last tested</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {visible.map((a) => (
                <tr key={a.id} className="cursor-pointer hover:bg-surface-2" onClick={() => router.push(`/admin/agents/${a.id}`)}>
                  <td className="px-3 py-2">
                    <Link href={`/admin/agents/${a.id}`} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>{a.name}</Link>{" "}
                    <span className="font-mono text-xs text-accent">{a.command}</span>
                    {defaultAgent === a.id ? <Badge tone="accent">default</Badge> : null}
                    <p className="truncate text-xs text-muted">{a.description}</p>
                  </td>
                  <td className="px-3 py-2 text-xs">{typeLabel(a.connection?.connection_type)}</td>
                  <td className="max-w-[220px] truncate px-3 py-2 text-xs text-muted">{a.connection?.api_endpoint ?? "—"}</td>
                  <td className="px-3 py-2 font-mono text-xs text-muted">{a.connection?.connection_type === "origin" ? "—" : a.connection?.configured ? a.connection.api_key_preview : <span className="text-warning">missing</span>}</td>
                  <td className="px-3 py-2"><ConnectionBadge agent={a} /></td>
                  <td className="px-3 py-2"><Badge tone={a.status === "active" ? "success" : "neutral"}>{a.status === "active" ? "on" : a.status}</Badge></td>
                  <td className="px-3 py-2 text-xs text-faint">{a.connection?.connection_tested_at ? new Date(a.connection.connection_tested_at).toLocaleString() : "never"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </AdminShell>
  );
}
