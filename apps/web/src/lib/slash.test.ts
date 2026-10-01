import { describe, expect, it } from "vitest";
import { matchAgents, parseSlash, splitCommand } from "./slash";

const agents = [
  { command: "/resize", name: "Resize Agent" },
  { command: "/creativeresize", name: "Creative Resize Agent" },
  { command: "/svg", name: "SVG Agent" },
];

describe("parseSlash", () => {
  it("selects an agent for a bare command without sending anything", () => {
    expect(parseSlash("/resize", agents)).toEqual({ kind: "select", command: "/resize", agent: agents[0] });
    expect(parseSlash("  /RESIZE  ", agents)).toMatchObject({ kind: "select", command: "/resize" });
  });
  it("sends the cleaned prompt to the named agent", () => {
    expect(parseSlash("/resize Resize this image into 4:5", agents)).toEqual({ kind: "send", command: "/resize", agent: agents[0], body: "Resize this image into 4:5" });
    expect(parseSlash("/creativeresize Make a creative\n4:5 adaptation", agents)).toMatchObject({ kind: "send", body: "Make a creative 4:5 adaptation" });
  });
  it("treats non-command text as plain", () => {
    expect(parseSlash("Make it 9:16 too", agents)).toEqual({ kind: "plain", text: "Make it 9:16 too" });
    expect(parseSlash("/ not a command", agents)).toEqual({ kind: "plain", text: "/ not a command" });
  });
  it("reports unknown commands with suggestions", () => {
    expect(parseSlash("/res", agents)).toMatchObject({ kind: "unknown", command: "/res", suggestions: [agents[0], agents[1]] });
    expect(parseSlash("/nope do it", agents)).toMatchObject({ kind: "unknown", suggestions: [] });
  });
});

describe("matchAgents", () => {
  it("matches command prefix first, then name substring", () => {
    expect(matchAgents("/res", agents).map((a) => a.command)).toEqual(["/resize", "/creativeresize"]);
    expect(matchAgents("svg", agents).map((a) => a.command)).toEqual(["/svg"]);
    expect(matchAgents("", agents)).toHaveLength(3);
  });
});

describe("splitCommand", () => {
  it("separates a leading command from the body", () => {
    expect(splitCommand("/resize make it 4:5")).toEqual({ command: "/resize", body: "make it 4:5" });
    expect(splitCommand("plain")).toEqual({ command: null, body: "plain" });
  });
});
