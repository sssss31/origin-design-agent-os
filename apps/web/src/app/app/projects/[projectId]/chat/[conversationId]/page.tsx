"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChatThread } from "@/components/chat/ChatThread";
import { RECENTS_CHANGED } from "@/components/shell/AppShell";
import { Composer } from "@/components/chat/Composer";
import { ExecutionPanel } from "@/components/chat/ExecutionPanel";
import { TopBar } from "@/components/TopBar";
import { Button } from "@/components/ui/Button";
import { ErrorText } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { assetsApi, conversationsApi, runsApi } from "@/lib/api/chat";
import { ApiError } from "@/lib/api/client";
import { subscribeRunEvents, type SseHandle } from "@/lib/sse";
import { deriveTimeline, type Timeline } from "@/lib/timeline";
import type { AssetOut, ConversationOut, EventOut, MessageOut } from "@/types/chat";

export default function ChatPage() {
  const { projectId, conversationId } = useParams<{ projectId: string; conversationId: string }>();
  const router = useRouter();
  const [conversations, setConversations] = useState<ConversationOut[]>([]);
  const [conversation, setConversation] = useState<ConversationOut | null>(null);
  const [messages, setMessages] = useState<MessageOut[]>([]);
  const [assets, setAssets] = useState<AssetOut[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  // events are kept per run so switching runs never needs a synchronous reset inside an effect
  const [eventsByRun, setEventsByRun] = useState<Record<string, EventOut[]>>({});
  const events = useMemo(() => (runId ? eventsByRun[runId] ?? [] : []), [eventsByRun, runId]);
  const timeline: Timeline | null = useMemo(() => (runId && events.length ? deriveTimeline(events) : null), [events, runId]);
  const [error, setError] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [title, setTitle] = useState("");
  const [panelOpen, setPanelOpen] = useState(false);
  const sse = useRef<SseHandle | null>(null);

  const loadMessages = useCallback(() => conversationsApi.messages(conversationId).then(setMessages).catch(() => undefined), [conversationId]);
  const loadSidebar = useCallback(() => conversationsApi.list(projectId).then(setConversations).catch(() => setConversations([])), [projectId]);

  useEffect(() => {
    void loadSidebar();
    assetsApi.list(projectId).then(setAssets).catch(() => setAssets([]));
  }, [projectId, loadSidebar]);

  useEffect(() => {
    conversationsApi.get(conversationId).then((c) => { setConversation(c); setTitle(c.title); }).catch(() => setConversation(null));
    void loadMessages();
    runsApi.list(conversationId).then((runs) => { const latest = runs[0]; if (latest) setRunId(latest.id); }).catch(() => undefined);
  }, [conversationId, loadMessages]);

  // subscribe to the selected run: replay persisted events, then tail live ones
  useEffect(() => {
    sse.current?.close();
    if (!runId) return;
    const collected: EventOut[] = [];
    sse.current = subscribeRunEvents(runId, {
      onEvent: (e) => {
        if (e.type === "clarification.requested") setPanelOpen(true);
        collected.push(e);
        setEventsByRun((prev) => ({ ...prev, [runId]: [...collected] }));
        if (e.type === "artifact.created" || e.type === "run.completed" || e.type === "clarification.received") void loadMessages();
      },
      onEnd: () => void loadMessages(),
    });
    return () => sse.current?.close();
  }, [runId, loadMessages]);

  const busy = Boolean(timeline && !timeline.terminal && timeline.runStatus !== "WAITING_FOR_USER");

  const send = async (content: string, assetIds: string[]) => {
    setError(null);
    try {
      const created = await runsApi.create(conversationId, { content, selected_asset_ids: assetIds });
      await loadMessages();
      void loadSidebar();
      window.dispatchEvent(new Event(RECENTS_CHANGED));
      setRunId(created.run_id);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.message}${err.code === "agent_unavailable" ? " — pick another command from the menu." : ""}` : "Could not start the run");
      await loadMessages();
    }
  };
  const act = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Request failed");
    }
  };

  return (
    <>
      <TopBar title={conversation?.title ?? "Chat"} />
      <div className="flex min-h-0 flex-1">
        <section className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center gap-3 border-b border-border px-4 py-1.5 text-xs">
            <Link href={`/app/projects/${projectId}`} className="font-medium text-muted hover:text-text">{conversations.find((c) => c.id === conversationId) ? "Project" : "Project"}</Link>
            <Link href={`/app/projects/${projectId}/assets`} className="text-muted hover:text-text">Assets ({assets.length})</Link>
            <Link href={`/app/projects/${projectId}/artifacts`} className="text-muted hover:text-text">Artifacts</Link>
            <button className="text-muted hover:text-text" onClick={() => void conversationsApi.create(projectId).then((c) => { window.dispatchEvent(new Event(RECENTS_CHANGED)); router.push(`/app/projects/${projectId}/chat/${c.id}`); })}>+ New chat here</button>
            <button className="text-muted hover:text-text xl:hidden" onClick={() => setPanelOpen((o) => !o)}>{panelOpen ? "Hide execution" : "Execution"}</button>
            <span className="mx-1 text-border-strong">|</span>
            {renaming ? (
              <>
                <Input value={title} onChange={(e) => setTitle(e.target.value)} className="max-w-xs" />
                <Button className="px-2 py-1 text-[11px]" onClick={() => void act(async () => { const c = await conversationsApi.update(conversationId, { title }); setConversation(c); setRenaming(false); void loadSidebar(); })}>Save</Button>
              </>
            ) : (
              <>
                <button className="text-muted hover:text-text" onClick={() => setRenaming(true)}>Rename</button>
                <button className="text-muted hover:text-text" onClick={() => void act(async () => { await conversationsApi.update(conversationId, { status: conversation?.status === "archived" ? "active" : "archived" }); router.push(`/app/projects/${projectId}`); })}>{conversation?.status === "archived" ? "Unarchive" : "Archive"}</button>
              </>
            )}
            <ErrorText>{error}</ErrorText>
          </div>
          <ChatThread messages={messages} activeRunId={runId} onOpenRun={setRunId} />
          <Composer assets={assets} busy={busy} onSend={send} onStop={runId ? () => void act(() => runsApi.cancel(runId)) : undefined} />
        </section>
        <ExecutionPanel runId={runId} timeline={timeline} events={events} open={panelOpen} onClose={() => setPanelOpen(false)} onAnswer={(a) => act(() => runsApi.clarify(runId!, a))} onCancel={() => act(() => runsApi.cancel(runId!))} onRetry={() => act(() => runsApi.retry(runId!))} />
      </div>
    </>
  );
}
