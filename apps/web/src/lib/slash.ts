/**
 * Slash-command parsing for the chat composer (brief §2). Pure, so it is unit-tested and shared
 * by the composer and the agent dropdown — both go through the same selection logic.
 */
export interface SlashAgent {
  command: string;
  name: string;
}

export type SlashIntent =
  | { kind: "plain"; text: string }
  | { kind: "select"; command: string; agent: SlashAgent } // "/resize"  → select, no run
  | { kind: "send"; command: string; agent: SlashAgent; body: string } // "/resize text" → switch + send
  | { kind: "unknown"; command: string; suggestions: SlashAgent[] }; // "/nope …" → helpful error

const COMMAND_RE = /^\/([a-z][a-z0-9_-]{0,39})$/i;

export function parseSlash(text: string, agents: SlashAgent[]): SlashIntent {
  const trimmed = text.trim();
  if (!trimmed.startsWith("/")) return { kind: "plain", text: trimmed };
  const [first, ...rest] = trimmed.split(/\s+/);
  if (!first || !COMMAND_RE.test(first)) return { kind: "plain", text: trimmed };
  const command = first.toLowerCase();
  const agent = agents.find((a) => a.command.toLowerCase() === command);
  if (!agent) return { kind: "unknown", command, suggestions: matchAgents(command, agents).slice(0, 3) };
  const body = rest.join(" ").trim();
  return body ? { kind: "send", command, agent, body } : { kind: "select", command, agent };
}

/** "/res" → Resize Agent, Creative Resize Agent — command prefix first, then name substring. */
export function matchAgents(query: string, agents: SlashAgent[]): SlashAgent[] {
  const q = query.toLowerCase().replace(/^\//, "");
  if (!q) return agents;
  const byCommand = agents.filter((a) => a.command.toLowerCase().replace(/^\//, "").startsWith(q));
  const byName = agents.filter((a) => !byCommand.includes(a) && a.name.toLowerCase().includes(q));
  return [...byCommand, ...byName];
}

/** The part of a stored message to show as text, with the command rendered separately as a chip. */
export function splitCommand(content: string): { command: string | null; body: string } {
  const m = /^(\/[a-z][a-z0-9_-]*)\s*([\s\S]*)$/i.exec(content.trim());
  return m ? { command: m[1] ?? null, body: m[2] ?? "" } : { command: null, body: content };
}
