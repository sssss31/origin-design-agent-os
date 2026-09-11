import { describe, expect, it } from "vitest";
import { deriveTimeline } from "@/lib/timeline";
import type { EventOut } from "@/types/chat";

const ev = (n: number, type: EventOut["type"], payload: EventOut["payload"] = {}): EventOut => ({ run_id: "r", sequence_no: n, type, occurred_at: "", node_run_id: null, payload });

describe("deriveTimeline", () => {
  it("projects node status from persisted events", () => {
    const t = deriveTimeline([
      ev(1, "run.started", { run_status: "RUNNING" }),
      ev(2, "node.started", { node_id: "parse", node_name: "Parse command", node_index: 0 }),
      ev(3, "node.completed", { node_id: "parse", node_status: "SUCCEEDED", duration_ms: 3 }),
      ev(4, "node.started", { node_id: "agent:resize", node_name: "Resize Agent", node_index: 2 }),
      ev(5, "tool.started", { node_id: "agent:resize", tool_slug: "image.resize" }),
      ev(6, "artifact.created", { node_id: "agent:resize", artifact_id: "a1", artifact_type: "image" }),
      ev(7, "clarification.requested", { node_id: "agent:resize", question: "Which sizes?", node_status: "WAITING_FOR_USER", run_status: "WAITING_FOR_USER" }),
    ]);
    expect(t.runStatus).toBe("WAITING_FOR_USER");
    expect(t.nodes.map((n) => [n.id, n.status])).toEqual([
      ["parse", "SUCCEEDED"],
      ["agent:resize", "WAITING_FOR_USER"],
    ]);
    expect(t.nodes[1]?.tools).toEqual(["image.resize"]);
    expect(t.artifactIds).toEqual(["a1"]);
    expect(t.pendingQuestion?.question).toBe("Which sizes?");
  });

  it("marks failure and terminal state", () => {
    const t = deriveTimeline([ev(1, "run.started"), ev(2, "node.started", { node_id: "x", node_name: "X" }), ev(3, "node.failed", { node_id: "x", error_message: "boom", retryable: true }), ev(4, "run.failed", { run_status: "FAILED" })]);
    expect(t.runStatus).toBe("FAILED");
    expect(t.nodes[0]?.error).toBe("boom");
    expect(t.terminal).toBe(true);
  });
});
