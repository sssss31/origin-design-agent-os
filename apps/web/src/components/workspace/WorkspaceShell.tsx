"use client";

import { Briefcase, FolderOpen, LogOut, MessageSquarePlus, Settings, Shield } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { RECENTS_CHANGED } from "@/components/shell/AppShell";
import { conversationsApi } from "@/lib/api/chat";
import { api } from "@/lib/api/client";
import { dashboardApi } from "@/lib/api/dashboard";
import { useSession } from "@/lib/session";
import type { RecentConversation } from "@/types/dashboard";

/** Workspace V0 §4: WORKSPACE | CHAT | ACTIVITY. This is the left column. */
export function WorkspaceShell({ children, activity }: { children: React.ReactNode; activity?: React.ReactNode }) {
  const session = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const [recents, setRecents] = useState<RecentConversation[]>([]);
  const load = useCallback(() => dashboardApi.recents({ limit: 40 }).then(setRecents).catch(() => setRecents([])), []);
  useEffect(() => {
    if (session.status !== "authenticated") return;
    void load();
    window.addEventListener(RECENTS_CHANGED, load);
    return () => window.removeEventListener(RECENTS_CHANGED, load);
  }, [session.status, pathname, load]);
  useEffect(() => {
    if (session.status === "anonymous") router.replace("/login");
  }, [session.status, router]);
  if (session.status !== "authenticated") return <div className="flex min-h-screen items-center justify-center text-sm text-muted">Loading…</div>;

  const newChat = async () => {
    const projects = (await api<{ projects: { id: string }[] }>("/library?limit=1")).projects;
    const projectId = projects[0]?.id;
    if (!projectId) {
      const out = await api<{ project_id: string; conversation_id: string }>("/quickstart", { method: "POST", body: { content: "/auto", title: "New chat" } }).catch(() => null);
      if (out) { router.push(`/chat/${out.conversation_id}`); return; }
      return;
    }
    const conv = await conversationsApi.create(projectId);
    window.dispatchEvent(new Event(RECENTS_CHANGED));
    router.push(`/chat/${conv.id}`);
  };
  const groups = groupByDay(recents);
  return (
    <div className="flex h-screen bg-bg">
      <aside className="flex w-64 shrink-0 flex-col border-r border-border bg-surface">
        <div className="p-3">
          <p className="mb-3 px-1 text-sm font-semibold">Origin <span className="text-[10px] font-normal uppercase tracking-wider text-faint">workspace</span></p>
          <button onClick={() => void newChat()} className="flex w-full items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:opacity-90"><MessageSquarePlus size={16} /> New Chat</button>
        </div>
        <nav className="px-2 text-sm">
          <Link href="/work" className={`flex items-center gap-2 rounded-md px-2 py-1.5 ${pathname.startsWith("/work") ? "bg-accent-soft text-accent" : "text-muted hover:bg-surface-2 hover:text-text"}`}><Briefcase size={15} /> My Work</Link>
          <Link href="/app/library" className="flex items-center gap-2 rounded-md px-2 py-1.5 text-muted hover:bg-surface-2 hover:text-text"><FolderOpen size={15} /> Files</Link>
        </nav>
        <div className="mt-3 min-h-0 flex-1 overflow-y-auto px-2">
          <p className="px-2 pb-1 text-[11px] font-medium uppercase tracking-wider text-faint">Chats</p>
          {recents.length === 0 ? <p className="px-2 text-xs text-faint">No chats yet</p> : null}
          {groups.map(([day, items]) => (
            <div key={day} className="mb-2">
              <p className="px-2 py-1 text-[10px] uppercase tracking-wider text-faint">{day}</p>
              {items.map((c) => (
                <Link key={c.id} href={`/chat/${c.id}`} className={`block truncate rounded-md px-2 py-1.5 text-[13px] ${pathname === `/chat/${c.id}` ? "bg-surface-2 text-text" : "text-muted hover:bg-surface-2 hover:text-text"}`} title={c.title}>{c.title}</Link>
              ))}
            </div>
          ))}
        </div>
        <div className="border-t border-border p-2 text-sm">
          {session.me?.capabilities.admin_console ? <Link href="/admin/agents" className="flex items-center gap-2 rounded-md px-2 py-1.5 text-muted hover:bg-surface-2 hover:text-text"><Shield size={15} /> Admin · Agents</Link> : null}
          <Link href="/app/account" className="flex items-center gap-2 rounded-md px-2 py-1.5 text-muted hover:bg-surface-2 hover:text-text"><Settings size={15} /> Settings</Link>
          <button onClick={async () => { await session.logout(); router.replace("/login"); }} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-muted hover:bg-surface-2 hover:text-text"><LogOut size={15} /> Sign out · {session.me?.user.display_name}</button>
        </div>
      </aside>
      <main className="flex min-w-0 flex-1 flex-col">{children}</main>
      {activity ? <aside className="hidden w-80 shrink-0 border-l border-border bg-surface xl:flex xl:flex-col">{activity}</aside> : null}
    </div>
  );
}

function groupByDay(rows: RecentConversation[]): [string, RecentConversation[]][] {
  const map = new Map<string, RecentConversation[]>();
  const today = new Date().toDateString();
  const yesterday = new Date(Date.now() - 86400000).toDateString();
  for (const r of rows) {
    const d = new Date(r.last_message_at ?? r.created_at).toDateString();
    const label = d === today ? "Today" : d === yesterday ? "Yesterday" : d;
    map.set(label, [...(map.get(label) ?? []), r]);
  }
  return [...map.entries()];
}
