"use client";

import { Bot, Check, CircleDashed, Crown, Download, Loader2, Maximize2, Minus, Plus, ScanSearch, Sparkles, Type, Wand2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { edgePath, layoutGraph, NODE_H, NODE_W, type Placed } from "@/lib/graph-layout";
import type { AgentGraph, GraphNode } from "@/types/dashboard";
import type { NodeState } from "@/types/events";

const ICONS: Record<string, typeof Bot> = { "/auto": Crown, "/master": Sparkles, "/resize": Maximize2, "/editable": Wand2, "/qc": ScanSearch, "/export": Download, "/copy": Type, "/asset": Bot };

const STATUS: Record<NodeState, { label: string; color: string; Icon: typeof Check; pulse?: boolean }> = {
  PENDING: { label: "queued", color: "var(--text-faint)", Icon: CircleDashed },
  RUNNING: { label: "running", color: "var(--info)", Icon: Loader2, pulse: true },
  WAITING_FOR_USER: { label: "needs you", color: "var(--warning)", Icon: CircleDashed, pulse: true },
  SUCCEEDED: { label: "done", color: "var(--success)", Icon: Check },
  FAILED: { label: "failed", color: "var(--danger)", Icon: X },
  SKIPPED: { label: "skipped", color: "var(--text-faint)", Icon: Minus },
};

export interface RunOverlay {
  statuses: Record<string, NodeState>;
  order: string[];
  active: boolean;
}

export function GraphCanvas({ graph, selected, onSelect, overlay }: { graph: AgentGraph; selected: GraphNode | null; onSelect: (n: GraphNode | null) => void; overlay?: RunOverlay | null }) {
  const { placed, width, height } = useMemo(() => layoutGraph(graph), [graph]);
  const byId = useMemo(() => new Map(placed.map((p) => [p.node.id, p])), [placed]);
  const container = useRef<HTMLDivElement>(null);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const [hover, setHover] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const drag = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);
  const [size, setSize] = useState({ w: 800, h: 520 });

  useEffect(() => {
    const el = container.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      if (entry) setSize({ w: entry.contentRect.width, h: entry.contentRect.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const fit = useCallback(() => {
    const k = Math.min(1.1, Math.max(0.35, Math.min((size.w - 40) / width, (size.h - 40) / height)));
    setView({ k, x: (size.w - width * k) / 2, y: (size.h - height * k) / 2 });
  }, [size, width, height]);
  useEffect(() => {
    const id = requestAnimationFrame(fit);
    return () => cancelAnimationFrame(id);
  }, [fit]);

  const zoomBy = (factor: number, cx = size.w / 2, cy = size.h / 2) =>
    setView((v) => {
      const k = Math.min(2.5, Math.max(0.3, v.k * factor));
      return { k, x: cx - ((cx - v.x) * k) / v.k, y: cy - ((cy - v.y) * k) / v.k };
    });

  const focus = selected?.id ?? hover;
  const related = useMemo(() => {
    if (!focus) return null;
    const s = new Set<string>([focus]);
    for (const e of graph.edges) {
      if (e.source === focus) s.add(e.target);
      if (e.target === focus) s.add(e.source);
    }
    return s;
  }, [focus, graph.edges]);

  const activeEdges = useMemo(() => {
    if (!overlay) return new Set<string>();
    const s = new Set<string>();
    for (let i = 1; i < overlay.order.length; i++) s.add(`${overlay.order[i - 1]}->${overlay.order[i]}`);
    return s;
  }, [overlay]);

  return (
    <div
      ref={container}
      className="relative h-[560px] w-full overflow-hidden rounded-card border border-border bg-surface"
      style={{ backgroundImage: "radial-gradient(var(--border-strong) 0.8px, transparent 0.8px)", backgroundSize: `${18 * view.k}px ${18 * view.k}px`, backgroundPosition: `${view.x}px ${view.y}px` }}
      onWheel={(e) => {
        e.preventDefault();
        const rect = container.current!.getBoundingClientRect();
        zoomBy(e.deltaY < 0 ? 1.1 : 0.9, e.clientX - rect.left, e.clientY - rect.top);
      }}
      onPointerDown={(e) => {
        if ((e.target as HTMLElement).closest("[data-node]")) return;
        drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y };
        setDragging(true);
        (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => {
        if (!drag.current) return;
        setView((v) => ({ ...v, x: drag.current!.vx + (e.clientX - drag.current!.x), y: drag.current!.vy + (e.clientY - drag.current!.y) }));
      }}
      onPointerUp={() => {
        drag.current = null;
        setDragging(false);
      }}
      onClick={(e) => {
        if (!(e.target as HTMLElement).closest("[data-node]")) onSelect(null);
      }}
    >
      <svg width={size.w} height={size.h} className="absolute inset-0 select-none" style={{ cursor: dragging ? "grabbing" : "grab" }}>
        <defs>
          <marker id="g-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="var(--border-strong)" /></marker>
          <marker id="g-arrow-hot" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="var(--accent)" /></marker>
          <marker id="g-arrow-fail" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="var(--danger)" /></marker>
          <style>{`@keyframes g-flow { to { stroke-dashoffset: -24; } } .g-flow { stroke-dasharray: 8 8; animation: g-flow 0.9s linear infinite; } @keyframes g-pulse { 0%,100% { opacity: .35 } 50% { opacity: 1 } } .g-pulse { animation: g-pulse 1.2s ease-in-out infinite; }`}</style>
        </defs>
        <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
          {graph.edges.map((e, i) => {
            const a = byId.get(e.source);
            const b = byId.get(e.target);
            if (!a || !b) return null;
            const { d } = edgePath(a, b);
            const key = `${a.node.slug}->${b.node.slug}`;
            const hot = activeEdges.has(key) || (related !== null && related.has(e.source) && related.has(e.target) && (focus === e.source || focus === e.target));
            const dim = related !== null && !hot;
            const stroke = e.is_failure_route ? "var(--danger)" : hot ? "var(--accent)" : "var(--border-strong)";
            return (
              <g key={i} opacity={dim ? 0.18 : 1}>
                <path d={d} fill="none" stroke={stroke} strokeWidth={hot ? 2.2 : 1.4} strokeDasharray={e.is_failure_route ? "5 5" : undefined} markerEnd={`url(#${e.is_failure_route ? "g-arrow-fail" : hot ? "g-arrow-hot" : "g-arrow"})`} />
                {hot && !e.is_failure_route ? <path d={d} fill="none" stroke="var(--accent)" strokeWidth={2.2} className="g-flow" opacity={0.9} /> : null}
              </g>
            );
          })}
          {placed.map((p) => (
            <NodeCard key={p.node.id} placed={p} selected={selected?.id === p.node.id} dim={related !== null && !related.has(p.node.id)} status={overlay?.statuses[p.node.slug]} onSelect={() => onSelect(p.node)} onHover={setHover} />
          ))}
        </g>
      </svg>
      <div className="absolute bottom-3 left-3 flex items-center gap-1 rounded-lg border border-border bg-surface/90 p-1 shadow-card backdrop-blur">
        <button className="rounded p-1.5 hover:bg-surface-2" onClick={() => zoomBy(1.2)} aria-label="Zoom in"><Plus size={14} /></button>
        <button className="rounded p-1.5 hover:bg-surface-2" onClick={() => zoomBy(0.83)} aria-label="Zoom out"><Minus size={14} /></button>
        <button className="rounded p-1.5 hover:bg-surface-2" onClick={fit} aria-label="Fit to view"><Maximize2 size={14} /></button>
        <span className="px-2 text-[11px] text-faint">{Math.round(view.k * 100)}%</span>
      </div>
      <div className="absolute bottom-3 right-3 flex items-center gap-3 rounded-lg border border-border bg-surface/90 px-3 py-1.5 text-[11px] text-muted shadow-card backdrop-blur">
        <span className="flex items-center gap-1"><span className="inline-block h-0.5 w-5 bg-border-strong" /> handoff</span>
        <span className="flex items-center gap-1"><span className="inline-block h-0.5 w-5 border-t border-dashed border-danger" /> QC failure route</span>
        {overlay ? <span className="flex items-center gap-1"><span className="inline-block h-0.5 w-5 bg-accent" /> this run</span> : null}
      </div>
    </div>
  );
}

function NodeCard({ placed, selected, dim, status, onSelect, onHover }: { placed: Placed; selected: boolean; dim: boolean; status?: NodeState; onSelect: () => void; onHover: (id: string | null) => void }) {
  const n = placed.node;
  const Icon = ICONS[n.command] ?? Bot;
  const st = status ? STATUS[status] : null;
  const border = selected ? "var(--accent)" : st ? st.color : n.is_manager ? "var(--accent)" : "var(--border)";
  return (
    <g data-node transform={`translate(${placed.x} ${placed.y})`} onClick={(e) => { e.stopPropagation(); onSelect(); }} onPointerEnter={() => onHover(n.id)} onPointerLeave={() => onHover(null)} className="cursor-pointer" opacity={dim ? 0.3 : 1} style={{ transition: "opacity .15s" }}>
      {selected || st?.pulse ? <rect x={-4} y={-4} width={NODE_W + 8} height={NODE_H + 8} rx={16} fill="none" stroke={border} strokeWidth={2} className={st?.pulse ? "g-pulse" : undefined} opacity={0.5} /> : null}
      <rect width={NODE_W} height={NODE_H} rx={13} fill="var(--surface)" stroke={border} strokeWidth={selected ? 2 : 1.3} style={{ filter: "drop-shadow(0 4px 14px rgba(0,0,0,0.10))" }} />
      <rect x={12} y={14} width={36} height={36} rx={10} fill={n.is_manager ? "var(--accent)" : "var(--accent-soft)"} />
      <foreignObject x={12} y={14} width={36} height={36}>
        <div className="flex h-9 w-9 items-center justify-center" style={{ color: n.is_manager ? "var(--accent-contrast)" : "var(--accent)" }}><Icon size={18} /></div>
      </foreignObject>
      <text x={58} y={28} fontSize={13} fontWeight={600} fill="var(--text)">{n.name.length > 20 ? n.name.slice(0, 19) + "…" : n.name}</text>
      <text x={58} y={45} fontSize={11} fontFamily="ui-monospace, SFMono-Regular, monospace" fill="var(--accent)">{n.command}</text>
      <text x={12} y={72} fontSize={10.5} fill="var(--text-muted)">{(n.model ?? "no model").slice(0, 16)} · v{n.version ?? "—"} · {n.tools.length} tools · {n.skills_count} skills</text>
      {n.tools.slice(0, 3).map((t, i) => (
        <g key={t} transform={`translate(${12 + i * 70} 78)`}>
          <rect width={64} height={13} rx={6} fill="var(--surface-2)" />
          <text x={32} y={9.5} fontSize={8.5} textAnchor="middle" fill="var(--text-muted)">{t.length > 13 ? t.slice(0, 12) + "…" : t}</text>
        </g>
      ))}
      {st ? (
        <g transform={`translate(${NODE_W - 70} 10)`}>
          <rect width={60} height={16} rx={8} fill="var(--surface-2)" />
          <foreignObject x={5} y={2} width={12} height={12}><div style={{ color: st.color }} className={st.pulse ? "animate-spin" : undefined}><st.Icon size={11} /></div></foreignObject>
          <text x={20} y={11.5} fontSize={9} fill={st.color} fontWeight={600}>{st.label}</text>
        </g>
      ) : n.status !== "active" ? (
        <text x={NODE_W - 12} y={20} fontSize={9.5} textAnchor="end" fill="var(--warning)">{n.status}</text>
      ) : null}
    </g>
  );
}
