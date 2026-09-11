"use client";

import { ArrowRight, Bot, Clock, Images } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ArtifactCard } from "@/components/chat/ArtifactCard";
import { HeroComposer } from "@/components/shell/HeroComposer";
import { commandsApi } from "@/lib/api/admin";
import { dashboardApi } from "@/lib/api/dashboard";
import { useSession } from "@/lib/session";
import type { CommandOut } from "@/types/admin";
import type { LibraryOut, RecentConversation } from "@/types/dashboard";

function Home() {
  const session = useSession();
  const params = useSearchParams();
  const [library, setLibrary] = useState<LibraryOut | null>(null);
  const [recents, setRecents] = useState<RecentConversation[]>([]);
  const [commands, setCommands] = useState<CommandOut[]>([]);
  useEffect(() => {
    dashboardApi.library({ limit: 12 }).then(setLibrary).catch(() => setLibrary({ artifacts: [], assets: [], projects: [] }));
    dashboardApi.recents({ limit: 6 }).then(setRecents).catch(() => setRecents([]));
    commandsApi.list().then(setCommands).catch(() => setCommands([]));
  }, [session.organizationId]);
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const first = session.me?.user.display_name.split(" ")[0] ?? "";

  return (
    <main className="flex-1 overflow-y-auto">
      <section className="px-8 pt-16 pb-10 text-center">
        <p className="text-sm text-muted">{greeting}, {first}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">What are we designing today?</h1>
        <p className="mx-auto mt-2 max-w-xl text-sm text-muted">One chat, eight specialist agents. Describe the deliverable, attach brand assets, and watch every step run live.</p>
        <div className="mt-8">
          <HeroComposer projects={library?.projects ?? []} autoFocus={params.get("compose") === "1"} />
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-8 pb-10">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-semibold"><Bot size={15} className="text-muted" /> Agents</h2>
          <Link href="/app/nodes" className="flex items-center gap-1 text-xs text-muted hover:text-text">See the pipeline <ArrowRight size={12} /></Link>
        </div>
        {commands.length === 0 ? (
          <div className="rounded-card border border-dashed border-border p-6 text-center text-sm text-muted">
            No agents are active yet. {session.me?.capabilities.admin_console ? <Link href="/admin" className="text-accent">Seed the eight design agents from the admin dashboard.</Link> : "Ask an administrator to publish agents."}
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {commands.map((c) => (
              <Link key={c.agent_id} href={`/app?compose=1`} className="group rounded-card border border-border bg-surface p-4 transition hover:-translate-y-0.5 hover:border-border-strong hover:shadow-card">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs text-accent">{c.command}</span>
                  {c.is_manager ? <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[10px] font-medium text-accent">manager</span> : null}
                </div>
                <p className="mt-2 text-sm font-medium">{c.name}</p>
                <p className="mt-1 line-clamp-2 text-xs text-muted">{c.description || "—"}</p>
              </Link>
            ))}
          </div>
        )}
      </section>

      <section className="mx-auto grid max-w-6xl gap-8 px-8 pb-16 lg:grid-cols-[1fr_1.2fr]">
        <div>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-semibold"><Clock size={15} className="text-muted" /> Recent chats</h2>
            <Link href="/app/history" className="flex items-center gap-1 text-xs text-muted hover:text-text">All history <ArrowRight size={12} /></Link>
          </div>
          {recents.length === 0 ? <p className="rounded-card border border-dashed border-border p-6 text-center text-sm text-muted">Your conversations will appear here.</p> : null}
          <ul className="space-y-2">
            {recents.map((c) => (
              <li key={c.id}>
                <Link href={`/app/projects/${c.project_id}/chat/${c.id}`} className="block rounded-card border border-border bg-surface px-4 py-3 transition hover:border-border-strong">
                  <p className="truncate text-sm font-medium">{c.title}</p>
                  <p className="mt-0.5 truncate text-xs text-muted">{c.last_message_preview ?? "—"}</p>
                  <p className="mt-1 text-[11px] text-faint">{c.workspace_name} / {c.project_name}{c.last_message_at ? ` · ${new Date(c.last_message_at).toLocaleString()}` : ""}</p>
                </Link>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-semibold"><Images size={15} className="text-muted" /> Latest artifacts</h2>
            <Link href="/app/library" className="flex items-center gap-1 text-xs text-muted hover:text-text">Open library <ArrowRight size={12} /></Link>
          </div>
          {library && library.artifacts.length === 0 ? <p className="rounded-card border border-dashed border-border p-6 text-center text-sm text-muted">Generated files land here with lineage and approval status.</p> : null}
          <div className="grid gap-2 sm:grid-cols-2">
            {library?.artifacts.slice(0, 6).map((a) => <ArtifactCard key={a.id} artifactId={a.id} initial={a} compact />)}
          </div>
        </div>
      </section>
    </main>
  );
}

export default function AppHome() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-muted">Loading…</div>}>
      <Home />
    </Suspense>
  );
}
