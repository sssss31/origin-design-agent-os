"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { assetsApi, conversationsApi, runsApi } from "@/lib/api/chat";
import { api, ApiError } from "@/lib/api/client";
import { dashboardApi } from "@/lib/api/dashboard";
import { subscribeRunEvents, type SseHandle } from "@/lib/sse";
import { deriveTimeline } from "@/lib/timeline";
import type { ConversationOut, EventOut, MessageOut } from "@/types/chat";
import type { LibraryOut } from "@/types/dashboard";

export const CHATS_CHANGED = "origin:chats-changed";
const TERMINAL = new Set(["SUCCEEDED", "FAILED", "CANCELLED"]);
const POLL_MS = 2000;

export interface PendingMessage {
  content: string;
  files: string[];
}

/** Readable text for an API failure (brief §21). */
export function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.code) {
      case "agent_unavailable":
        return "Agent not found. Type / to see the available agents.";
      case "empty_prompt":
        return "Type the command followed by your request, e.g. /resize make it 4:5.";
      case "agent_auth":
        return "Agent authentication failed. Check its token in Admin → Agents.";
      case "agent_rate_limited":
        return "The agent is rate-limited right now. Retry in a moment.";
      case "agent_timeout":
        return "The agent request timed out. Retry.";
      case "quota_exceeded":
        return "Daily run quota reached for this organisation.";
      default:
        return err.message || "Request failed";
    }
  }
  return "Could not reach the server. Check your connection and retry.";
}

/**
 * All state for one chat. The backend is the source of truth: messages, the active agent and runs
 * are always re-read from the API; local state only adds the optimistic user bubble and the live
 * stream. Nothing here navigates away or clears messages because of an error.
 */
export function useConversation(conversationId: string | null) {
  const router = useRouter();
  const [conversation, setConversation] = useState<ConversationOut | null>(null);
  const [messages, setMessages] = useState<MessageOut[]>([]);
  const [loaded, setLoaded] = useState(!conversationId);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingMessage | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [runKey, setRunKey] = useState(0);
  const [active, setActive] = useState(false);
  const [events, setEvents] = useState<EventOut[]>([]);
  const [streamText, setStreamText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const sse = useRef<SseHandle | null>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(async () => {
    if (!conversationId) return;
    const [c, m] = await Promise.all([conversationsApi.get(conversationId), conversationsApi.messages(conversationId)]);
    setConversation(c);
    setMessages(m);
    setPending(null);
    setLoaded(true);
    setLoadError(null);
  }, [conversationId]);

  // initial load + refresh recovery (brief §15): re-attach to a run that is still going
  useEffect(() => {
    if (!conversationId) return;
    Promise.resolve()
      .then(() => refresh())
      .then(() => runsApi.list(conversationId))
      .then((runs) => {
        const latest = runs[0];
        if (!latest) return;
        if (!TERMINAL.has(latest.status)) {
          setRunId(latest.id);
          setActive(true);
        } else if (latest.status === "FAILED") {
          setRunId(latest.id);
          setError(latest.error_json?.message ?? "The agent could not complete the request. Retry.");
        }
      })
      .catch((err: unknown) => {
        setLoaded(true);
        setLoadError(describeError(err));
      });
  }, [conversationId, refresh]);

  // live events: SSE first; if the stream drops before the run ends, fall back to polling history
  useEffect(() => {
    sse.current?.close();
    if (pollTimer.current) clearTimeout(pollTimer.current);
    if (!runId || !active) return;
    const collected: EventOut[] = [];
    let text = "";
    let finished = false;
    const absorb = (e: EventOut) => {
      if (collected.some((x) => x.sequence_no === e.sequence_no)) return;
      collected.push(e);
      collected.sort((a, b) => a.sequence_no - b.sequence_no);
      setEvents([...collected]);
      if (e.type === "response.streaming" && e.payload.delta) {
        text += e.payload.delta;
        setStreamText(text);
      }
      if (e.type === "run.completed" || e.type === "run.failed" || e.type === "run.cancelled") {
        // A retried run keeps its earlier events, so a terminal event in the replay may belong to a
        // previous attempt. The run's status is the source of truth.
        void runsApi
          .get(runId)
          .then((run) => {
            if (!TERMINAL.has(run.status) || finished) return;
            finished = true;
            if (run.status === "FAILED") setError(run.error_json?.message ?? "The agent could not complete the request. Retry.");
            setActive(false);
            setStreamText("");
            void refresh();
            window.dispatchEvent(new Event(CHATS_CHANGED));
          })
          .catch(() => undefined);
      }
    };
    const poll = async () => {
      if (finished) return;
      try {
        const last = collected.length ? collected[collected.length - 1]!.sequence_no : 0;
        const history = await runsApi.history(runId, last);
        history.forEach(absorb);
        if (!finished) {
          const run = await runsApi.get(runId); // the server reaps stale runs here (brief §15)
          if (TERMINAL.has(run.status)) {
            finished = true;
            setActive(false);
            setStreamText("");
            if (run.status === "FAILED") setError(run.error_json?.message ?? "The agent run was interrupted. Retry.");
            await refresh();
            return;
          }
        }
      } catch {
        /* keep polling */
      }
      if (!finished) pollTimer.current = setTimeout(() => void poll(), POLL_MS);
    };
    sse.current = subscribeRunEvents(runId, {
      onEvent: absorb,
      onEnd: () => {
        if (!finished) void poll();
      },
      onError: () => {
        if (!finished) void poll();
      },
    });
    return () => {
      sse.current?.close();
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, [runId, runKey, active, refresh]);

  const timeline = useMemo(() => (events.length ? deriveTimeline(events) : null), [events]);

  /** Create the conversation lazily (home screen) and return its id. */
  const ensureConversation = async (): Promise<{ id: string; projectId: string | null; created: boolean }> => {
    if (conversationId) return { id: conversationId, projectId: conversation?.project_id ?? null, created: false };
    const lib = await api<LibraryOut>("/library?limit=1");
    const projectId = lib.projects[0]?.id ?? null;
    if (projectId) {
      const c = await conversationsApi.create(projectId); // the server titles it from the first request
      return { id: c.id, projectId, created: true };
    }
    const out = await dashboardApi.quickstart({ content: "/auto hello", title: "New chat" });
    return { id: out.conversation_id, projectId: out.project_id, created: true };
  };

  const send = async (content: string, files: File[]) => {
    setError(null);
    try {
      const target = await ensureConversation();
      setPending({ content, files: files.map((f) => f.name) });
      const assetIds: string[] = [];
      for (const f of files) assetIds.push((await assetsApi.upload(target.projectId as string, f)).id);
      const created = await runsApi.create(target.id, { content, selected_asset_ids: assetIds });
      window.dispatchEvent(new Event(CHATS_CHANGED));
      if (target.created) {
        router.push(`/c/${target.id}`); // the new page re-attaches to the queued run
        return;
      }
      setEvents([]);
      setStreamText("");
      setRunId(created.run_id);
      setRunKey((k) => k + 1);
      setActive(true);
      await refresh();
    } catch (err) {
      setPending(null);
      setError(describeError(err));
    }
  };

  /** "/resize" alone, or the dropdown: switch the active agent without sending anything. */
  const select = async (command: string) => {
    setError(null);
    try {
      const target = await ensureConversation();
      const c = await conversationsApi.setActiveAgent(target.id, { command });
      if (target.created) {
        router.push(`/c/${target.id}`);
        return;
      }
      setConversation(c);
      await refresh(); // picks up the persistent "Agent selected" event
    } catch (err) {
      setError(describeError(err));
    }
  };

  const retry = async () => {
    if (!runId) return;
    setError(null);
    try {
      const run = await runsApi.retry(runId); // re-runs the same stored message; nothing is duplicated
      setEvents([]);
      setStreamText("");
      setRunId(run.id);
      setRunKey((k) => k + 1);
      setActive(true);
    } catch (err) {
      setError(describeError(err));
    }
  };

  const stop = async () => {
    if (!runId) return;
    try {
      await runsApi.cancel(runId);
    } catch {
      /* already finished */
    }
  };

  const reload = () => {
    setLoadError(null);
    void refresh().catch((err: unknown) => setLoadError(describeError(err)));
  };

  return { conversation, messages, loaded, loadError, reload, pending, busy: active, streamText, timeline, error, send, select, retry, stop };
}
