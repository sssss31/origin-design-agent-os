"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Composer } from "@/components/chat/Composer";
import { RECENTS_CHANGED } from "@/components/shell/AppShell";
import { ChatThread } from "@/components/chat/ChatThread";
import { ActivityPanel } from "@/components/workspace/ActivityPanel";
import { WorkspaceShell } from "@/components/workspace/WorkspaceShell";
import { Badge, ErrorText } from "@/components/ui/Card";
import { assetsApi, conversationsApi, runsApi } from "@/lib/api/chat";
import { ApiError } from "@/lib/api/client";
import { subscribeRunEvents, type SseHandle } from "@/lib/sse";
import { deriveTimeline, type Timeline } from "@/lib/timeline";
import type { AssetOut, ConversationOut, EventOut, MessageOut } from "@/types/chat";

/** Workspace V0 §4: CHAT column with agent mentions, streaming reply and active agent. */
export default function WorkspaceChatPage() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const [conversation, setConversation] = useState<ConversationOut | null>(null);
  const [messages, setMessages] = useState<MessageOut[]>([]);
  const [assets, setAssets] = useState<AssetOut[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [events, setEvents] = useState<EventOut[]>([]);
  const [streaming, setStreaming] = useState<{ agent: string | null; text: string } | null>(null);
  const [switchNote, setSwitchNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sse = useRef<SseHandle | null>(null);
  const prevAgent = useRef<string | null>(null);

  const loadMessages = useCallback(() => conversationsApi.messages(conversationId).then(setMessages).catch(() => setMessages([])), [conversationId]);
  const loadConversation = useCallback(
    () =>
      conversationsApi.get(conversationId).then((c) => {
        setConversation(c);
        const now = c.active_agent?.name ?? null;
        if (prevAgent.current && now && prevAgent.current !== now) setSwitchNote(`Active Agent changed: ${prevAgent.current} → ${now}`);
        prevAgent.current = now;
        return c;
      }),
    [conversationId],
  );
  useEffect(() => {
    void loadConversation().then((c) => assetsApi.list(c.project_id).then(setAssets).catch(() => setAssets([])));
    void loadMessages();
    runsApi.list(conversationId).then((runs) => { const latest = runs[0]; if (latest) setRunId(latest.id); }).catch(() => undefined);
  }, [conversationId, loadConversation, loadMessages]);

  useEffect(() => {
    sse.current?.close();
    if (!runId) return;
    const collected: EventOut[] = [];
    let text = "";
    sse.current = subscribeRunEvents(runId, {
      onEvent: (e) => {
        collected.push(e);
        setEvents(collected.length === 1 ? [e] : [...collected]);
        if (e.type === "response.streaming" && e.payload.delta) {
          text += e.payload.delta;
          setStreaming({ agent: e.payload.agent_slug ?? null, text });
        }
        if (e.type === "run.completed" || e.type === "run.failed" || e.type === "run.cancelled") {
          setStreaming(null);
          void loadMessages();
          void loadConversation();
        }
      },
      onEnd: () => { setStreaming(null); void loadMessages(); },
    });
    return () => sse.current?.close();
  }, [runId, loadMessages, loadConversation]);

  const timeline: Timeline | null = useMemo(() => (events.length ? deriveTimeline(events) : null), [events]);
  const busy = Boolean(timeline && !timeline.terminal && timeline.runStatus !== "WAITING_FOR_USER");

  const send = async (content: string, assetIds: string[]) => {
    setError(null);
    setSwitchNote(null);
    try {
      const created = await runsApi.create(conversationId, { content, selected_asset_ids: assetIds });
      await loadMessages();
      void loadConversation();
      window.dispatchEvent(new Event(RECENTS_CHANGED));
      setRunId(created.run_id);
    } catch (err) {
      if (err instanceof ApiError && err.code === "agent_unavailable") setError("Agent not found. Type / to see the available agents.");
      else setError(err instanceof ApiError ? err.message : "Could not send the message");
    }
  };
  const act = async (fn: () => Promise<unknown>) => { setError(null); try { await fn(); } catch (err) { setError(err instanceof ApiError ? err.message : "Request failed"); } };
  const activeMemory = conversation?.memory.find((m) => m.agent_id === conversation.active_agent?.id);

  return (
    <WorkspaceShell activity={<ActivityPanel runId={runId} timeline={timeline} events={events} onRetry={runId ? () => void act(() => runsApi.retry(runId).then(() => setRunId(runId))) : undefined} onCancel={runId ? () => void act(() => runsApi.cancel(runId)) : undefined} />}>
      <header className="flex h-12 items-center gap-3 border-b border-border bg-surface px-4">
        <h1 className="truncate text-sm font-semibold">{conversation?.title ?? "Chat"}</h1>
        {conversation?.active_agent ? <Badge tone="accent">Active Agent · {conversation.active_agent.name} {conversation.active_agent.command}</Badge> : <Badge>No agent yet — type /</Badge>}
        {activeMemory?.turns ? <span className="text-[11px] text-faint">{activeMemory.turns} turns of context</span> : null}
      </header>
      {switchNote ? <p className="border-b border-border bg-accent-soft px-4 py-1 text-center text-xs text-accent">{switchNote}</p> : null}
      <ChatThread messages={messages} activeRunId={runId} onOpenRun={setRunId} />
      {streaming ? (
        <div className="px-4 pb-2">
          <div className="max-w-[75%] rounded-lg border border-border bg-surface px-3 py-2 text-sm">
            <p className="mb-1 text-[11px] text-muted"><Badge tone="accent">{conversation?.active_agent?.name ?? streaming.agent ?? "agent"}</Badge> streaming…</p>
            <p className="whitespace-pre-wrap">{streaming.text}</p>
          </div>
        </div>
      ) : null}
      <div className="px-4"><ErrorText>{error}</ErrorText></div>
      <Composer
        assets={assets}
        busy={busy}
        onSend={send}
        onStop={runId && busy ? () => void act(() => runsApi.cancel(runId)) : undefined}
        activeAgent={conversation?.active_agent ?? null}
        memoryTurns={activeMemory?.turns ?? 0}
        onActivate={(command) => act(async () => { setConversation(await conversationsApi.setActiveAgent(conversationId, { command })); void loadConversation(); })}
        onClearMemory={() => act(async () => setConversation(await conversationsApi.clearMemory(conversationId, conversation?.active_agent?.id)))}
      />
    </WorkspaceShell>
  );
}
