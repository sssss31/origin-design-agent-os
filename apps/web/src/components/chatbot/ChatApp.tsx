"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Composer } from "@/components/chatbot/Composer";
import { Sidebar } from "@/components/chatbot/Sidebar";
import { Thread } from "@/components/chatbot/Thread";
import { useConversation } from "@/components/chatbot/useConversation";
import { commandsApi } from "@/lib/api/admin";
import { useSession } from "@/lib/session";
import type { CommandOut } from "@/types/admin";

/** The whole product: a Claude-style chat where /agent talks straight to a connected GPT agent. */
export function ChatApp({ conversationId }: { conversationId: string | null }) {
  const session = useSession();
  const router = useRouter();
  const [agents, setAgents] = useState<CommandOut[]>([]);
  useEffect(() => {
    if (session.status === "anonymous") router.replace("/login");
  }, [session.status, router]);
  useEffect(() => {
    if (session.status !== "authenticated") return;
    commandsApi.list().then((list) => setAgents(list.filter((a) => !a.is_manager))).catch(() => setAgents([]));
  }, [session.status]);
  if (session.status !== "authenticated") return <div className="flex min-h-screen items-center justify-center text-sm text-muted">Loading…</div>;
  return (
    <div className="flex h-screen bg-bg text-text">
      <Sidebar currentId={conversationId} />
      <Conversation key={conversationId ?? "new"} conversationId={conversationId} agents={agents} firstName={(session.me?.user.display_name || "").split(" ")[0] || null} />
    </div>
  );
}

function Conversation({ conversationId, agents, firstName }: { conversationId: string | null; agents: CommandOut[]; firstName: string | null }) {
  const chat = useConversation(conversationId);
  const activeAgent = chat.conversation?.active_agent ?? null;
  const agentName = activeAgent?.name ?? "Agent";
  const empty = !conversationId || (chat.messages.length === 0 && !chat.pending && !chat.busy);
  return (
    <main className="flex min-w-0 flex-1 flex-col">
      {empty ? (
        <div className="flex flex-1 flex-col items-center justify-center px-4">
          <h1 className="mb-6 text-center text-3xl font-semibold tracking-tight">{firstName ? `Hi ${firstName}, what should we work on?` : "What should we work on?"}</h1>
          <div className="w-full">
            <Composer agents={agents} activeAgent={activeAgent} busy={chat.busy} autoFocus onSend={chat.send} onStop={chat.stop} />
          </div>
          {agents.length ? (
            <div className="mt-2 flex max-w-3xl flex-wrap justify-center gap-2">
              {agents.map((a) => (
                <span key={a.agent_id} className="rounded-full border border-border px-3 py-1 text-xs text-muted" title={a.description}><span className="font-mono text-accent">{a.command}</span> {a.name}</span>
              ))}
            </div>
          ) : (
            <p className="mt-2 text-xs text-faint">No agents connected yet. An admin can add them under Agents & API keys.</p>
          )}
          {chat.error ? <p className="mt-3 text-sm text-danger">{chat.error}</p> : null}
        </div>
      ) : (
        <>
          <header className="flex h-12 items-center gap-3 px-5">
            <h1 className="truncate text-sm font-medium">{chat.conversation?.title ?? "Chat"}</h1>
            {activeAgent ? <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[11px] text-accent">{activeAgent.name} <span className="font-mono">{activeAgent.command}</span></span> : null}
          </header>
          <Thread messages={chat.messages} pending={chat.pending} busy={chat.busy} streamText={chat.streamText} timeline={chat.timeline} agentName={agentName} error={chat.error} onRetry={() => void chat.retry()} />
          <Composer agents={agents} activeAgent={activeAgent} busy={chat.busy} autoFocus onSend={chat.send} onStop={chat.stop} />
        </>
      )}
    </main>
  );
}
