import type { AgentGraph, GraphNode } from "@/types/dashboard";

export interface Placed {
  node: GraphNode;
  x: number;
  y: number;
  layer: number;
}

export const NODE_W = 232;
export const NODE_H = 96;
const GAP_X = 130;
const GAP_Y = 36;
const ORDER = ["/auto", "/asset", "/copy", "/master", "/resize", "/editable", "/qc", "/export"];

/**
 * Layered left-to-right layout (a small Sugiyama): layer = longest path from a root over
 * forward (non-failure) handoffs, so Manager → producers → QC → Export reads left to right.
 * Nodes in a layer are ordered by the canonical design pipeline order, then by name.
 */
export function layoutGraph(graph: AgentGraph): { placed: Placed[]; width: number; height: number } {
  const ids = graph.nodes.map((n) => n.id);
  const forward = graph.edges.filter((e) => !e.is_failure_route && e.source !== e.target);
  const incoming = new Map<string, number>(ids.map((id) => [id, 0]));
  for (const e of forward) incoming.set(e.target, (incoming.get(e.target) ?? 0) + 1);
  const layer = new Map<string, number>();
  // longest-path layering with cycle protection
  const visiting = new Set<string>();
  const depth = (id: string): number => {
    if (layer.has(id)) return layer.get(id)!;
    if (visiting.has(id)) return 0;
    visiting.add(id);
    const parents = forward.filter((e) => e.target === id).map((e) => e.source);
    const d = parents.length ? Math.max(...parents.map((p) => depth(p) + 1)) : 0;
    visiting.delete(id);
    layer.set(id, d);
    return d;
  };
  ids.forEach((id) => depth(id));
  // QC and Export tend to be reachable from everything; pin them to the last two layers for readability
  const maxLayer = Math.max(0, ...layer.values());
  for (const n of graph.nodes) {
    if (n.command === "/qc" && maxLayer >= 2) layer.set(n.id, Math.max(layer.get(n.id) ?? 0, maxLayer - 1));
    if (n.command === "/export" && maxLayer >= 2) layer.set(n.id, maxLayer);
  }
  const byLayer = new Map<number, GraphNode[]>();
  for (const n of graph.nodes) {
    const l = layer.get(n.id) ?? 0;
    byLayer.set(l, [...(byLayer.get(l) ?? []), n]);
  }
  const rank = (n: GraphNode) => {
    const i = ORDER.indexOf(n.command);
    return i === -1 ? 100 : i;
  };
  const layers = [...byLayer.keys()].sort((a, b) => a - b);
  const tallest = Math.max(1, ...layers.map((l) => byLayer.get(l)!.length));
  const height = 80 + tallest * (NODE_H + GAP_Y);
  const placed: Placed[] = [];
  for (const l of layers) {
    const nodes = byLayer.get(l)!.sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
    const total = nodes.length * NODE_H + (nodes.length - 1) * GAP_Y;
    const top = (height - total) / 2;
    nodes.forEach((n, i) => placed.push({ node: n, layer: l, x: 60 + l * (NODE_W + GAP_X), y: top + i * (NODE_H + GAP_Y) }));
  }
  const width = 120 + layers.length * (NODE_W + GAP_X);
  return { placed, width: Math.max(width, 600), height: Math.max(height, 360) };
}

/** Cubic bezier between the right edge of `a` and the left edge of `b`; back-edges loop underneath. */
export function edgePath(a: Placed, b: Placed): { d: string; back: boolean } {
  const x1 = a.x + NODE_W;
  const y1 = a.y + NODE_H / 2;
  const x2 = b.x;
  const y2 = b.y + NODE_H / 2;
  if (x2 >= x1) {
    const c = Math.max(50, (x2 - x1) / 2);
    return { d: `M ${x1} ${y1} C ${x1 + c} ${y1}, ${x2 - c} ${y2}, ${x2} ${y2}`, back: false };
  }
  // failure / return route: leave from the bottom, travel under the row, enter the target from below
  const yb = Math.max(a.y, b.y) + NODE_H + 40 + Math.abs(a.layer - b.layer) * 10;
  const sx = a.x + NODE_W / 2;
  const tx = b.x + NODE_W / 2;
  return { d: `M ${sx} ${a.y + NODE_H} C ${sx} ${yb}, ${tx} ${yb}, ${tx} ${b.y + NODE_H}`, back: true };
}
