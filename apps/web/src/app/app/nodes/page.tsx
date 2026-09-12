"use client";

import { Activity, ExternalLink, Radio } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { GraphCanvas, type RunOverlay } from "@/components/nodes/GraphCanvas";
import { PageHeader } from "@/components/shell/PageHeader";
import { Badge, Card, CardTitle } from "@/components/ui/Card";
import { Select } from "@/components/ui/JsonField";
import { runsApi } from "@/lib/api/chat";
import { dashboardApi } from "@/lib/api/dashboard";
import { useSession } from "@/lib/session";
import { subscribeRunEvents, type SseHandle } from "@/lib/sse";
import type { AgentGraph, GraphNode, RecentRun } from "@/types/dashboard";
import type { NodeState } from "@/types/events";

const TERMINAL = new Set(["SUCCEEDED", "FAILED", "CANCELLED"]);

export default function NodesPage() {
  const session = useSession();
  const [graph, setGraph] = useState<AgentGraph | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [runs, setRuns] = useState<RecentRun[]>([]);
  const [runId, setRunId] = useState("");
  const [statuses, setStatuses] = useState<Record<string, NodeState>>({});
  const [order, setOrder] = useState<string[]>([]);
  const [runStatus, setRunStatus] = useState<string | null>(null);
  const sse = useRef<SseHandle | null>(null);

  useEffect(() => {
    dashboardApi.graph().then(setGraph).catch(() => setGraph({ nodes: [], edges: [] }));
    dashboardApi.recentRuns(20).then(setRuns).catch(() => setRuns([]));
  }, [session.organizationId]);

  // live overlay: seed statuses from the run, then tail events while it is active
  useEffect(() => {
    sse.current?.close();
    if (!runId) return;
    const run = runs.find((r) => r.id === runId);
    if (!run) return;
    const slugById = new Map((graph?.nodes ?? []).map((n) => [n.id, n.slug]));
    const initial: Record<string, NodeState> = {};
    for (const [slug, st] of Object.entries(run.node_statuses)) initial[slug] = st as NodeState;
    const seq: string[] = [...run.agent_slugs];
    const id = requestAnimationFrame(() => {
      setStatuses(initial);
      setOrder(seq);
      setRunStatus(run.status);
    });
    if (TERMINAL.has(run.status)) return () => cancelAnimationFrame(id);
    sse.current = subscribeRunEvents(runId, {
      onEvent: (e) => {
        const p = e.payload;
        if (p.agent_slug && e.type === "agent.started") {
          setStatuses((s) => ({ ...s, [p.agent_slug!]: "RUNNING" }));
          setOrder((o) => (o.includes(p.agent_slug!) ? o : [...o, p.agent_slug!]));
        }
        if (e.type === "node.completed" || e.type === "node.failed" || e.type === "clarification.requested") {
          void runsApi.get(runId).then((r) => {
            const next: Record<string, NodeState> = {};
            for (const n of r.nodes) {
              const slug = n.agent_id ? slugById.get(n.agent_id) : null;
              if (slug) next[slug] = n.status;
            }
            setStatuses(next);
            setRunStatus(r.status);
          });
        }
        if (p.run_status) setRunStatus(p.run_status);
      },
    });
    return () => {
      cancelAnimationFrame(id);
      sse.current?.close();
    };
  }, [runId, runs, graph]);

  const overlay: RunOverlay | null = useMemo(() => (runId ? { statuses, order, active: runStatus !== null && !TERMINAL.has(runStatus) } : null), [runId, statuses, order, runStatus]);
  const isAdmin = session.me?.capabilities.admin_console ?? false;
  const current = runs.find((r) => r.id === runId);

  return (
    <main className="flex-1 overflow-y-auto">
      <PageHeader
        title="Nodes"
        subtitle="Your agent pipeline as it is configured right now. Pick a run to replay how work flowed through it — active runs animate live."
        actions={
          <>
            <div className="w-72">
              <Select
                value={runId}
                onChange={setRunId}
                options={[{ value: "", label: "Overlay a run…" }, ...runs.map((r) => ({ value: r.id, label: `${r.command ?? "auto"} · ${r.status.toLowerCase()} · ${r.conversation_title.slice(0, 28)}` }))]}
              />
            </div>
            {isAdmin ? <Link href="/admin/agents" className="rounded-md border border-border px-3 py-1.5 text-xs hover:bg-surface-2">Edit agents</Link> : null}
          </>
        }
      />
      <div className="grid gap-4 px-8 pb-10 xl:grid-cols-[1fr_320px]">
        <div>
          {graph ? (
            graph.nodes.length ? <GraphCanvas graph={graph} selected={selected} onSelect={setSelected} overlay={overlay} /> : <Card className="p-10 text-center text-sm text-muted">No agents configured yet.{isAdmin ? <> Seed them from the <Link href="/admin" className="text-accent">admin dashboard</Link>.</> : null}</Card>
          ) : (
            <Card className="h-[560px] animate-pulse"><span className="sr-only">Loading pipeline…</span></Card>
          )}
          {current ? (
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted">
              {overlay?.active ? <Radio size={12} className="text-accent" /> : <Activity size={12} />}
              <span className="font-medium text-text">{current.command ?? "/auto"}</span>
              <span className="truncate">{current.user_input}</span>
              <Badge tone={runStatus === "SUCCEEDED" ? "success" : runStatus === "FAILED" ? "danger" : runStatus === "WAITING_FOR_USER" ? "warning" : "accent"}>{runStatus ?? current.status}</Badge>
              <Link href={`/app/projects/${current.project_id}/chat/${current.conversation_id}`} className="ml-auto flex items-center gap-1 text-accent">Open chat <ExternalLink size={12} /></Link>
            </div>
          ) : null}
        </div>
        <div className="space-y-3">
          <Card>
            <CardTitle>{selected ? selected.name : "Select a node"}</CardTitle>
            {selected ? (
              <div className="space-y-2 text-sm">
                <p className="text-muted">{selected.description || "—"}</p>
                <p><span className="text-muted">Command</span> <span className="font-mono text-accent">{selected.command}</span></p>
                <p><span className="text-muted">Model</span> {selected.model ?? "—"} · <span className="text-muted">version</span> {selected.version ?? "draft"} · <span className="text-muted">skills</span> {selected.skills_count}</p>
                <div className="flex flex-wrap gap-1">{selected.tools.map((t) => <Badge key={t}>{t}</Badge>)}{selected.tools.length === 0 ? <span className="text-xs text-faint">no tools bound</span> : null}</div>
                <div>
                  <p className="mb-1 text-xs text-muted">Hands off to</p>
                  <ul className="space-y-0.5 text-xs">
                    {graph?.edges.filter((e) => e.source === selected.id).map((e) => {
                      const t = graph.nodes.find((n) => n.id === e.target);
                      return <li key={e.target}><span className="font-mono text-accent">{t?.command}</span> {e.is_failure_route ? <Badge tone="danger">failure route</Badge> : null} <span className="text-faint">{e.routing_hint}</span></li>;
                    })}
                    {graph && graph.edges.filter((e) => e.source === selected.id).length === 0 ? <li className="text-faint">none — this agent ends the chain</li> : null}
                  </ul>
                </div>
                {overlay?.statuses[selected.slug] ? <p className="text-xs">In this run: <Badge>{overlay.statuses[selected.slug]}</Badge></p> : null}
                {isAdmin ? <Link href={`/admin/agents/${selected.id}`} className="inline-block text-xs text-accent">Open in admin editor →</Link> : null}
              </div>
            ) : <p className="text-xs text-muted">Click a node to see its model, tools, skills and handoffs. Hover to highlight its connections. Drag to pan, scroll to zoom.</p>}
          </Card>
          <Card>
            <CardTitle>Recent runs</CardTitle>
            {runs.length === 0 ? <p className="text-xs text-muted">No runs yet — start one from Home.</p> : null}
            <ul className="space-y-1">
              {runs.slice(0, 8).map((r) => (
                <li key={r.id}>
                  <button onClick={() => setRunId(r.id)} className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs hover:bg-surface-2 ${runId === r.id ? "bg-accent-soft" : ""}`}>
                    <span className={`h-2 w-2 shrink-0 rounded-full ${r.status === "SUCCEEDED" ? "bg-success" : r.status === "FAILED" ? "bg-danger" : r.status === "WAITING_FOR_USER" ? "bg-warning" : "bg-info"}`} />
                    <span className="font-mono text-accent">{r.command ?? "/auto"}</span>
                    <span className="truncate text-muted">{r.user_input}</span>
                    <span className="ml-auto shrink-0 text-faint">{r.agent_slugs.length} agents</span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </main>
  );
}
