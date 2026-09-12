import { describe, expect, it } from "vitest";
import { edgePath, layoutGraph, NODE_W } from "@/lib/graph-layout";
import type { AgentGraph } from "@/types/dashboard";

const node = (id: string, command: string, is_manager = false) => ({ id, name: id, slug: id, command, description: "", is_manager, status: "active", version: 1, model: "m", tools: [], skills_count: 0 });

describe("layoutGraph", () => {
  it("places manager left, producers next, qc then export, and keeps failure routes as back-edges", () => {
    const graph: AgentGraph = {
      nodes: [node("manager", "/auto", true), node("resize", "/resize"), node("master", "/master"), node("qc", "/qc"), node("export", "/export")],
      edges: [
        { source: "manager", target: "resize", routing_hint: "", is_failure_route: false },
        { source: "manager", target: "master", routing_hint: "", is_failure_route: false },
        { source: "resize", target: "qc", routing_hint: "", is_failure_route: false },
        { source: "master", target: "qc", routing_hint: "", is_failure_route: false },
        { source: "qc", target: "export", routing_hint: "", is_failure_route: false },
        { source: "qc", target: "resize", routing_hint: "", is_failure_route: true },
      ],
    };
    const { placed } = layoutGraph(graph);
    const layer = (id: string) => placed.find((p) => p.node.id === id)!.layer;
    expect(layer("manager")).toBe(0);
    expect(layer("master")).toBe(1);
    expect(layer("resize")).toBe(1);
    expect(layer("qc")).toBe(2);
    expect(layer("export")).toBe(3);
    const master = placed.find((p) => p.node.id === "master")!;
    const resize = placed.find((p) => p.node.id === "resize")!;
    expect(master.y).toBeLessThan(resize.y); // canonical pipeline order within a layer
    const qc = placed.find((p) => p.node.id === "qc")!;
    expect(edgePath(resize, qc).back).toBe(false);
    expect(edgePath(qc, resize).back).toBe(true);
    expect(edgePath(resize, qc).d.startsWith(`M ${resize.x + NODE_W}`)).toBe(true);
  });

  it("survives cycles and empty graphs", () => {
    const graph: AgentGraph = { nodes: [node("a", "/a"), node("b", "/b")], edges: [{ source: "a", target: "b", routing_hint: "", is_failure_route: false }, { source: "b", target: "a", routing_hint: "", is_failure_route: false }] };
    expect(layoutGraph(graph).placed).toHaveLength(2);
    expect(layoutGraph({ nodes: [], edges: [] }).placed).toHaveLength(0);
  });
});
