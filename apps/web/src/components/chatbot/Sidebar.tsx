"use client";

import { ChevronsLeft, ChevronsRight, LogOut, MessageSquarePlus, MoreHorizontal, Search, Settings, ShieldCheck, SunMoon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { CHATS_CHANGED } from "@/components/chatbot/useConversation";
import { conversationsApi } from "@/lib/api/chat";
import { dashboardApi } from "@/lib/api/dashboard";
import { useSession } from "@/lib/session";
import { applyTheme, readTheme, type ThemeChoice } from "@/lib/theme";
import type { RecentConversation } from "@/types/dashboard";

function bucket(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const days = Math.floor((start - new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()) / 86_400_000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return "Previous 7 days";
  if (days < 30) return "Previous 30 days";
  return "Older";
}

export function Sidebar({ currentId }: { currentId: string | null }) {
  const session = useSession();
  const router = useRouter();
  const [open, setOpen] = useState(true);
  const [search, setSearch] = useState("");
  const [chats, setChats] = useState<RecentConversation[]>([]);
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const [accountOpen, setAccountOpen] = useState(false);
  const load = useCallback(() => dashboardApi.recents({ limit: 100, search: search || undefined }).then(setChats).catch(() => setChats([])), [search]);
  useEffect(() => {
    if (session.status !== "authenticated") return;
    const t = setTimeout(() => void load(), 150);
    window.addEventListener(CHATS_CHANGED, load);
    return () => {
      clearTimeout(t);
      window.removeEventListener(CHATS_CHANGED, load);
    };
  }, [session.status, load]);

  const rename = async (c: RecentConversation) => {
    const title = window.prompt("Rename chat", c.title);
    setMenuFor(null);
    if (!title || title === c.title) return;
    await conversationsApi.update(c.id, { title });
    void load();
  };
  const remove = async (c: RecentConversation) => {
    setMenuFor(null);
    if (!window.confirm(`Delete “${c.title}”?`)) return;
    await conversationsApi.update(c.id, { status: "archived" });
    if (c.id === currentId) router.push("/");
    void load();
  };
  const cycleTheme = () => {
    const order: ThemeChoice[] = ["system", "light", "dark"];
    const next = order[(order.indexOf(readTheme()) + 1) % order.length] ?? "system";
    applyTheme(next);
  };

  const groups = new Map<string, RecentConversation[]>();
  for (const c of chats) {
    const key = bucket(c.last_message_at ?? c.updated_at);
    groups.set(key, [...(groups.get(key) ?? []), c]);
  }
  const me = session.me?.user;
  const isAdmin = Boolean(session.me?.capabilities.admin_console);

  if (!open) {
    return (
      <aside className="flex w-14 shrink-0 flex-col items-center gap-2 border-r border-border bg-surface-2 py-3">
        <button onClick={() => setOpen(true)} className="rounded-md p-2 text-muted hover:bg-surface-3" aria-label="Open sidebar"><ChevronsRight size={18} /></button>
        <Link href="/" className="rounded-md p-2 text-muted hover:bg-surface-3" aria-label="New chat"><MessageSquarePlus size={18} /></Link>
      </aside>
    );
  }
  return (
    <aside className="flex w-[268px] shrink-0 flex-col border-r border-border bg-surface-2">
      <div className="flex items-center justify-between px-3 pt-3">
        <Link href="/" className="px-1 text-base font-semibold tracking-tight">Origin</Link>
        <button onClick={() => setOpen(false)} className="rounded-md p-1.5 text-muted hover:bg-surface-3" aria-label="Collapse sidebar"><ChevronsLeft size={16} /></button>
      </div>
      <div className="px-3 pt-3">
        <Link href="/" className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm font-medium text-accent hover:bg-surface-3"><MessageSquarePlus size={16} /> New chat</Link>
        <label className="mt-1 flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm text-muted hover:bg-surface-3">
          <Search size={15} />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search chats" className="w-full bg-transparent text-sm text-text outline-none placeholder:text-faint" />
        </label>
      </div>
      <nav className="mt-2 flex-1 overflow-y-auto px-3 pb-3">
        {chats.length === 0 ? <p className="px-2.5 pt-3 text-xs text-faint">{search ? "No chats match" : "Your chats will appear here"}</p> : null}
        {[...groups.entries()].map(([label, items]) => (
          <div key={label} className="mt-3">
            <p className="px-2.5 pb-1 text-[11px] font-medium uppercase tracking-wide text-faint">{label}</p>
            {items.map((c) => (
              <div key={c.id} className={`group relative flex items-center rounded-lg ${c.id === currentId ? "bg-surface-3" : "hover:bg-surface-3"}`}>
                <Link href={`/c/${c.id}`} className="min-w-0 flex-1 truncate px-2.5 py-1.5 text-sm">{c.title}</Link>
                <button onClick={() => setMenuFor(menuFor === c.id ? null : c.id)} className="mr-1 rounded p-1 text-faint opacity-0 hover:text-text group-hover:opacity-100" aria-label="Chat options"><MoreHorizontal size={14} /></button>
                {menuFor === c.id ? (
                  <div className="absolute right-0 top-8 z-20 w-36 rounded-lg border border-border bg-surface p-1 text-sm shadow-lg">
                    <button onClick={() => void rename(c)} className="w-full rounded px-2 py-1 text-left hover:bg-surface-2">Rename</button>
                    <button onClick={() => void remove(c)} className="w-full rounded px-2 py-1 text-left text-danger hover:bg-surface-2">Delete</button>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ))}
      </nav>
      <div className="relative border-t border-border p-2">
        <button onClick={() => setAccountOpen((v) => !v)} className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left hover:bg-surface-3">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent text-xs font-semibold text-accent-contrast">{(me?.display_name || me?.email || "?").slice(0, 1).toUpperCase()}</span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium">{me?.display_name || me?.email}</span>
            <span className="block truncate text-[11px] text-faint">{isAdmin ? "Admin" : "Member"}</span>
          </span>
        </button>
        {accountOpen ? (
          <div className="absolute bottom-14 left-2 right-2 z-20 rounded-lg border border-border bg-surface p-1 text-sm shadow-lg">
            <p className="truncate px-2 py-1 text-xs text-faint">{me?.email}</p>
            {isAdmin ? <Link href="/settings/agents" onClick={() => setAccountOpen(false)} className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-surface-2"><Settings size={14} /> Agents & API keys</Link> : null}
            <button onClick={cycleTheme} className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-surface-2"><SunMoon size={14} /> Toggle theme</button>
            {isAdmin ? <Link href="/admin" onClick={() => setAccountOpen(false)} className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-surface-2"><ShieldCheck size={14} /> Advanced console</Link> : null}
            <button onClick={() => void session.logout().then(() => router.replace("/login"))} className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-surface-2"><LogOut size={14} /> Sign out</button>
          </div>
        ) : null}
      </div>
    </aside>
  );
}
