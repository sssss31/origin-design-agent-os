import { describe, expect, it } from "vitest";
import { parseSseChunk } from "@/lib/sse";

describe("parseSseChunk", () => {
  it("handles CRLF and LF frames and keeps partial data", () => {
    const state = { buffer: "" };
    const first = parseSseChunk(state, 'id: 1\r\nevent: run.started\r\ndata: {"sequence_no":1,"type":"run.started"}\r\n\r\nid: 2\nevent: node.started\ndata: {"seq');
    expect(first.map((f) => f.type)).toEqual(["run.started"]);
    const second = parseSseChunk(state, 'uence_no":2,"type":"node.started"}\n\n');
    expect(second.map((f) => f.type)).toEqual(["node.started"]);
    expect(state.buffer).toBe("");
  });
});
