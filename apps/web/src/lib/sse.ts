/**
 * Fetch-based Server-Sent Events client.
 *
 * The browser's EventSource cannot send an Authorization header, so we read the stream with
 * fetch and parse `id:` / `event:` / `data:` frames ourselves. Reconnects resume from the
 * last sequence number through the `after` query parameter (same semantics as
 * Last-Event-ID), so a refresh or a dropped connection never loses or duplicates events.
 */

import { API_BASE } from "@/lib/api/client";
import { tokenStore } from "@/lib/token-store";
import type { EventOut } from "@/types/chat";

export interface SseHandle {
  close: () => void;
}

export interface SseParseState {
  buffer: string;
}

/** Pure framing step: appends a chunk and returns every complete `data:` payload parsed as JSON. */
export function parseSseChunk(state: SseParseState, chunk: string): EventOut[] {
  state.buffer += chunk.replace(/\r\n/g, "\n");
  const out: EventOut[] = [];
  let idx: number;
  while ((idx = state.buffer.indexOf("\n\n")) >= 0) {
    const frame = state.buffer.slice(0, idx);
    state.buffer = state.buffer.slice(idx + 2);
    let data = "";
    for (const line of frame.split("\n")) {
      if (line.startsWith("data:")) data += line.slice(5).trim();
    }
    if (!data) continue;
    try {
      out.push(JSON.parse(data) as EventOut);
    } catch {
      /* ignore malformed frame */
    }
  }
  return out;
}

export function subscribeRunEvents(runId: string, opts: { after?: number; onEvent: (e: EventOut) => void; onEnd?: () => void; onError?: (err: unknown) => void }): SseHandle {
  const controller = new AbortController();
  let last = opts.after ?? 0;
  let closed = false;
  let attempt = 0;

  const connect = async () => {
    while (!closed) {
      const headers: Record<string, string> = { Accept: "text/event-stream" };
      const token = tokenStore.getAccessToken();
      if (token) headers.Authorization = `Bearer ${token}`;
      const org = tokenStore.getOrganizationId();
      if (org) headers["X-Organization-Id"] = org;
      try {
        const res = await fetch(`${API_BASE}/runs/${runId}/events?after=${last}`, { headers, signal: controller.signal });
        if (!res.ok || !res.body) throw new Error(`stream failed with ${res.status}`);
        attempt = 0;
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        const state: SseParseState = { buffer: "" };
        let ended = false;
        while (!closed) {
          const { value, done } = await reader.read();
          if (done) break;
          for (const event of parseSseChunk(state, decoder.decode(value, { stream: true }))) {
            if (event.sequence_no <= last) continue;
            last = event.sequence_no;
            opts.onEvent(event);
            if (event.type === "run.completed" || event.type === "run.failed" || event.type === "run.cancelled") ended = true;
          }
        }
        if (ended || closed) {
          opts.onEnd?.();
          return;
        }
      } catch (err) {
        if (closed) return;
        opts.onError?.(err);
      }
      attempt += 1;
      await new Promise((r) => setTimeout(r, Math.min(1000 * 2 ** attempt, 10000)));
    }
  };
  void connect();
  return {
    close: () => {
      closed = true;
      controller.abort();
    },
  };
}
