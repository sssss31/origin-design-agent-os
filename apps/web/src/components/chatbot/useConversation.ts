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

export interface PendingMessage {
  content: string;
  files: string[];
}

function titleFrom(content: string): string {
  const t = content.replace(/^\/[a-z0-9_-]+\s*/i, "").trim();
  return (t.length > 60 ? `${t.slice(0, 57)}…` : t) || "New chat";
}

/** All state for one chat: messages, the current run's stream and the composer actions. */
export function useConversation(conversationId: string | null) {
  const router = useRouter();
  const [conversation, setConversation] = useState<ConversationOut | null>(null);
  const [messages, setMessages] = useState<MessageOut[]>([]);
  const [pending, setPending] = useState<PendingMessage | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [runKey, setRunKey] = useState(0);
  const [active, setActive] = useState(false);
  const [events, setEvents] = useState<EventOut[]>([]);
  const [streamText, setStreamText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const sse = useRef<SseHandle | null>(null);

  const refresh = useCallback(async () => {
    if (!conversationId) return;
    const [c, m] = await Promise.all([conversationsApi.get(conversationId), conversationsApi.messages(conversationId)]);
    setConversation(c);
    setMessages(m);
    setPending(null);
  }, [conversationId]);

  useEffect(() => {
    if (!conversationId) return;
    Promise.resolve()
      .then(() => refresh())
      .catch(() => router.replace("/"));
    runsApi
      .list(conversationId)
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
      .catch(() => undefined);
  }, [conversationId, refresh, router]);

  useEffect(() => {
    sse.current?.close();
    if (!runId || !active) return;
    const collected: EventOut[] = [];
    let text = "";
    sse.current = subscribeRunEvents(runId, {
      onEvent: (e) => {
        collected.push(e);
        setEvents([...collected]);
        if (e.type === "response.streaming" && e.payload.delta) {
          text += e.payload.delta;
          setStreamText(text);
        }
        if (e.type === "run.failed") setError(e.payload.error_message ?? "The agent could not complete the request. Retry.");
        if (e.type === "run.completed" || e.type === "run.failed" || e.type === "run.cancelled") {
          setActive(false);
          setStreamText("");
          void refresh();
          window.dispatchEvent(new Event(CHATS_CHANGED));
        }
      },
      onEnd: () => {
        setActive(false);
        setStreamText("");
        void refresh();
      },
      onError: () => {
        setActive(false);
        void refresh();
      },
    });
    return () => sse.current?.close();
  }, [runId, runKey, active, refresh]);

  const timeline = useMemo(() => (events.length ? deriveTimeline(events) : null), [events]);

  const send = async (content: string, files: File[]) => {
      setError(null);
      try {
        let convId = conversationId;
        let projectId = conversation?.project_id ?? null;
        if (!convId) {
          const lib = await api<LibraryOut>("/library?limit=1");
          projectId = lib.projects[0]?.id ?? null;
          if (projectId) {
            convId = (await conversationsApi.create(projectId, titleFrom(content))).id;
          } else {
            const out = await dashboardApi.quickstart({ content, title: titleFrom(content) });
            window.dispatchEvent(new Event(CHATS_CHANGED));
            router.push(`/c/${out.conversation_id}`);
            return;
          }
        }
        setPending({ content, files: files.map((f) => f.name) });
        const assetIds: string[] = [];
        for (const f of files) assetIds.push((await assetsApi.upload(projectId as string, f)).id);
        const created = await runsApi.create(convId, { content, selected_asset_ids: assetIds });
        window.dispatchEvent(new Event(CHATS_CHANGED));
        if (convId !== conversationId) {
          router.push(`/c/${convId}`);
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
        if (err instanceof ApiError && err.code === "agent_unavailable") setError("Agent not found. Type / to see the available agents.");
        else setError(err instanceof Error ? err.message : "Could not send the message");
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
      setError(err instanceof Error ? err.message : "Retry failed");
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

  const pickAgent = async (command: string | null) => {
    if (!conversationId) return;
    setConversation(await conversationsApi.setActiveAgent(conversationId, { command }));
  };

  return { conversation, messages, pending, busy: active, streamText, timeline, error, send, retry, stop, pickAgent };
}
