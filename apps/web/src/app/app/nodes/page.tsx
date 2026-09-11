"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/shell/PageHeader";
import { Badge, Card, CardTitle } from "@/components/ui/Card";
import { dashboardApi } from "@/lib/api/dashboard";
import { useSession } from "@/lib/session";
import type { AgentGraph, GraphNode } from "@/types/dashboard";

const W = 190;
const H = 72;

/** Lay the manager in the centre-left and specialists in a column to its right; other nodes below. */
function layout(graph: AgentGraph): Map<string, { x: number; y: number }> {
  const pos = new Map<string, { x: number; y: number }>();
  const manager = graph.nodes.find((n) => n.is_manager);
  const targets = manager ? graph.edges.filter((e) => e.source === manager.id && !e.is_failure_route).map((e) => e.target) : [];
  const specialists = graph.nodes.filter((n) => targets.includes(n.id));
  const others = graph.nodes.filter((n) => !n.is_manager && !targets.includes(n.id));
  const gapY = 96;
  specialists.forEach((n, i) => pos.set(n.id, { x: 360, y: 40 + i * gapY }));
  if (manager) pos.set(manager.id, { x: 40, y: Math.max(40, ((specialists.length - 1) * gapY) / 2 + 40) });
  others.forEach((n, i) => pos.set(n.id, { x: 40 + (i % 2) * 320, y: 40 + specialists.length * gapY + Math.floor(i / 2) * gapY }));
  return pos;
}

export default function NodesPage() {
  const session = useSession();
  const [graph, setGraph] = useState<AgentGraph | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  useEffect(() => {
    dashboardApi.graph().then(setGraph).catch(() => setGraph({ nodes: [], edges: [] }));
  }, [session.organizationId]);
  const pos = useMemo(() => (graph ? layout(graph) : new Map()), [graph]);
  const height = graph ? Math.max(360, ...[...pos.values()].map((p) => p.y + H + 40)) : 360;
  const isAdmin = session.me?.capabilities.admin_console ?? false;
  return (
    <main className="flex-1 overflow-y-auto">
      <PageHeader title="Nodes" subtitle="The agent pipeline as configured right now: every node is an agent version, every edge an allowed handoff. Dashed red edges are QC failure routes." actions={isAdmin ? <Link href="/admin/agents" className="rounded-md border border-border px-3 py-1.5 text-xs hover:bg-surface-2">Edit agents</Link> : null} />
      <div className="grid gap-4 px-8 pb-10 lg:grid-cols-[1fr_320px]">
        <Card className="overflow-x-auto p-2">
          {graph && graph.nodes.length === 0 ? <p className="p-8 text-center text-sm text-muted">No agents configured yet.</p> : null}
          {graph ? (
            <svg width={Math.max(640, 40 + 360 + W + 40)} height={height} className="min-w-full">
              <defs>
                <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="var(--border-strong)" /></marker>
                <marker id="arrow-fail" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="var(--danger)" /></marker>
              </defs>
              {graph.edges.map((e, i) => {
                const a = pos.get(e.source);
                const b = pos.get(e.target);
                if (!a || !b) return null;
                const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x, y2 = b.y + H / 2;
                const back = x2 < x1;
                const d = back ? `M ${a.x} ${y1} C ${a.x - 60} ${y1}, ${b.x + W + 60} ${y2}, ${b.x + W} ${y2}` : `M ${x1} ${y1} C ${x1 + 60} ${y1}, ${x2 - 60} ${y2}, ${x2} ${y2}`;
                return <path key={i} d={d} fill="none" stroke={e.is_failure_route ? "var(--danger)" : "var(--border-strong)"} strokeWidth={1.5} strokeDasharray={e.is_failure_route ? "5 4" : undefined} markerEnd={`url(#${e.is_failure_route ? "arrow-fail" : "arrow"})`} opacity={selected && selected.id !== e.source && selected.id !== e.target ? 0.25 : 1} />;
              })}
              {graph.nodes.map((n) => {
                const p = pos.get(n.id)!;
                const active = selected?.id === n.id;
                return (
                  <g key={n.id} transform={`translate(${p.x} ${p.y})`} onClick={() => setSelected(n)} className="cursor-pointer">
                    <rect width={W} height={H} rx={12} fill="var(--surface)" stroke={active ? "var(--accent)" : n.is_manager ? "var(--accent)" : "var(--border)"} strokeWidth={active ? 2 : 1.2} />
                    <text x={14} y={24} fontSize={12} fontWeight={600} fill="var(--text)">{n.name}</text>
                    <text x={14} y={42} fontSize={11} fontFamily="ui-monospace, monospace" fill="var(--accent)">{n.command}</text>
                    <text x={14} y={58} fontSize={10} fill="var(--text-muted)">{n.model ?? "no model"} · v{n.version ?? "—"} · {n.tools.length} tools</text>
                    {n.status !== "active" ? <text x={W - 14} y={22} fontSize={10} textAnchor="end" fill="var(--warning)">{n.status}</text> : null}
                  </g>
                );
              })}
            </svg>
          ) : <p className="p-8 text-sm text-muted">Loading…</p>}
        </Card>
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
                  <ul className="text-xs">{graph?.edges.filter((e) => e.source === selected.id).map((e) => { const t = graph.nodes.find((n) => n.id === e.target); return <li key={e.target}>{t?.command} {e.is_failure_route ? <Badge tone="danger">failure route</Badge> : null} <span className="text-faint">{e.routing_hint}</span></li>; })}</ul>
                </div>
                {isAdmin ? <Link href={`/admin/agents/${selected.id}`} className="inline-block text-xs text-accent">Open in admin editor →</Link> : null}
              </div>
            ) : <p className="text-xs text-muted">Click a node to see its model, tools, skills and handoffs.</p>}
          </Card>
          <Card>
            <CardTitle>How a run flows</CardTitle>
            <ol className="list-decimal space-y-1 pl-4 text-xs text-muted">
              <li>Parse the slash command (or route via the Manager).</li>
              <li>Load context: project summary, brand config, assets, approved artifacts, recent turns.</li>
              <li>Run the agent version with its skills and only its bound tools.</li>
              <li>Persist every produced file as a versioned artifact; QC can send work back once.</li>
              <li>Save the reply to the chat — every step is streamed live and replayable.</li>
            </ol>
          </Card>
        </div>
      </div>
    </main>
  );
}
