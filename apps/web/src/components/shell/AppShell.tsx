"use client";

import {
  Bot,
  ChevronLeft,
  ChevronRight,
  Clock,
  FolderKanban,
  History,
  Images,
  LayoutGrid,
  LogOut,
  MessageSquare,
  Plus,
  Search,
  Settings,
  Shield,
  Sparkles,
  Upload,
  Wand2,
  Workflow,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { conversationsApi } from "@/lib/api/chat";
import { api } from "@/lib/api/client";
import { useSession } from "@/lib/session";
import type { RecentConversation } from "@/types/dashboard";

const NAV = [
  { href: "/app", label: "Home", icon: LayoutGrid, exact: true },
  { href: "/app/workspaces", label: "Workspace", icon: FolderKanban },
  { href: "/app/skills", label: "Customize Skills", icon: Wand2 },
  { href: "/app/nodes", label: "Nodes", icon: Workflow },
  { href: "/app/chat", label: "Chat", icon: MessageSquare },
  { href: "/app/library", label: "Library", icon: Images },
  { href: "/app/history", label: "Chat History", icon: History },
] as const;

export const RECENTS_CHANGED = "origin:recents-changed";

export function AppShell({ children }: { children: React.ReactNode }) {
  const session = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [recents, setRecents] = useState<RecentConversation[]>([]);
  const [newOpen, setNewOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const newRef = useRef<HTMLDivElement>(null);
  const accountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const id = requestAnimationFrame(() => {
      try {
        setCollapsed(localStorage.getItem("origin.sidebar") === "collapsed");
      } catch {
        /* ignore */
      }
    });
    return () => cancelAnimationFrame(id);
  }, []);
  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    try {
      localStorage.setItem("origin.sidebar", next ? "collapsed" : "open");
    } catch {
      /* ignore */
    }
  };

  const loadRecents = useCallback(() => api<RecentConversation[]>("/conversations/recent?limit=12").then(setRecents).catch(() => setRecents([])), []);
  useEffect(() => {
    if (session.status !== "authenticated") return;
    void loadRecents();
    window.addEventListener(RECENTS_CHANGED, loadRecents);
    return () => window.removeEventListener(RECENTS_CHANGED, loadRecents);
  }, [session.status, session.organizationId, pathname, loadRecents]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (newRef.current && !newRef.current.contains(e.target as Node)) setNewOpen(false);
      if (accountRef.current && !accountRef.current.contains(e.target as Node)) setAccountOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  useEffect(() => {
    if (session.status === "anonymous") router.replace("/login");
  }, [session.status, router]);

  const isAdmin = session.me?.capabilities.admin_console ?? false;
  const initials = useMemo(() => (session.me?.user.display_name ?? "?").split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase(), [session.me]);

  const startNewChat = async () => {
    setNewOpen(false);
    const list = await api<{ id: string; name: string }[]>("/library").then((l) => (l as unknown as { projects: { id: string; name: string }[] }).projects).catch(() => []);
    if (list.length === 0) {
      router.push("/app?compose=1");
      return;
    }
    const project = list[0]!;
    const conv = await conversationsApi.create(project.id);
    window.dispatchEvent(new Event(RECENTS_CHANGED));
    router.push(`/app/projects/${project.id}/chat/${conv.id}`);
  };

  if (session.status !== "authenticated") {
    return <div className="flex min-h-screen items-center justify-center text-sm text-muted">Loading…</div>;
  }

  const width = collapsed ? "w-[var(--sidebar-rail)]" : "w-[var(--sidebar-w)]";
  return (
    <div className="flex min-h-screen bg-bg">
      <aside className={`${width} sticky top-0 flex h-screen shrink-0 flex-col border-r border-border bg-surface transition-[width] duration-200`}>
        {/* brand + collapse */}
        <div className={`flex items-center ${collapsed ? "justify-center" : "justify-between"} px-3 pt-3 pb-2`}>
          <Link href="/app" className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-accent-contrast"><Sparkles size={16} /></span>
            {!collapsed ? (
              <span className="leading-tight">
                <span className="block text-sm font-semibold">Origin</span>
                <span className="block text-[10px] uppercase tracking-wider text-faint">Design Agent OS</span>
              </span>
            ) : null}
          </Link>
          {!collapsed ? <button onClick={toggle} aria-label="Collapse sidebar" className="rounded-md p-1 text-faint hover:bg-surface-2 hover:text-text"><ChevronLeft size={16} /></button> : null}
        </div>
        {collapsed ? <button onClick={toggle} aria-label="Expand sidebar" className="mx-auto mb-1 rounded-md p-1 text-faint hover:bg-surface-2 hover:text-text"><ChevronRight size={16} /></button> : null}

        {/* + New */}
        <div ref={newRef} className="relative px-3 pb-2">
          <button onClick={() => setNewOpen((o) => !o)} className={`flex w-full items-center ${collapsed ? "justify-center" : "gap-2"} rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast shadow-card hover:opacity-90`} title="New">
            <Plus size={16} /> {!collapsed ? "New" : null}
          </button>
          {newOpen ? (
            <div className="fade-up absolute left-3 top-full z-30 mt-1 w-56 rounded-lg border border-border bg-surface p-1 shadow-card">
              <MenuItem icon={MessageSquare} label="New chat" hint="Start in your latest project" onClick={() => void startNewChat()} />
              <MenuItem icon={Sparkles} label="Design something" hint="Home composer with modes" onClick={() => { setNewOpen(false); router.push("/app?compose=1"); }} />
              <MenuItem icon={Upload} label="Upload asset" hint="Logos, images, PDFs, fonts" onClick={() => { setNewOpen(false); router.push("/app/library?tab=assets&upload=1"); }} />
              <MenuItem icon={FolderKanban} label="New workspace / project" onClick={() => { setNewOpen(false); router.push("/app/workspaces"); }} />
            </div>
          ) : null}
        </div>

        {/* primary nav */}
        <nav className="space-y-0.5 px-2">
          {NAV.map((item) => {
            const active = "exact" in item && item.exact ? pathname === item.href : item.href === "/app" ? pathname === "/app" : pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <Link key={item.href} href={item.href} title={item.label} className={`flex items-center ${collapsed ? "justify-center" : "gap-3"} rounded-lg px-2.5 py-2 text-sm transition ${active ? "bg-accent-soft font-medium text-accent" : "text-muted hover:bg-surface-2 hover:text-text"}`}>
                <Icon size={17} strokeWidth={1.8} />
                {!collapsed ? item.label : null}
              </Link>
            );
          })}
        </nav>

        {/* recents */}
        {!collapsed ? (
          <div className="mt-4 min-h-0 flex-1 overflow-y-auto px-2">
            <div className="flex items-center justify-between px-2.5 pb-1 text-[11px] font-medium uppercase tracking-wider text-faint">
              <span className="flex items-center gap-1"><Clock size={11} /> Recent</span>
              <Link href="/app/history" className="hover:text-text">All</Link>
            </div>
            {recents.length === 0 ? <p className="px-2.5 text-xs text-faint">No chats yet</p> : null}
            {recents.map((c) => {
              const href = `/app/projects/${c.project_id}/chat/${c.id}`;
              const active = pathname === href;
              return (
                <Link key={c.id} href={href} className={`block truncate rounded-md px-2.5 py-1.5 text-[13px] ${active ? "bg-surface-2 text-text" : "text-muted hover:bg-surface-2 hover:text-text"}`} title={`${c.project_name} · ${c.title}`}>
                  {c.title}
                </Link>
              );
            })}
          </div>
        ) : <div className="flex-1" />}

        {/* account footer */}
        <div ref={accountRef} className="relative border-t border-border p-2">
          <button onClick={() => setAccountOpen((o) => !o)} className={`flex w-full items-center ${collapsed ? "justify-center" : "gap-2"} rounded-lg px-2 py-2 text-left hover:bg-surface-2`}>
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-3 text-xs font-semibold">{initials}</span>
            {!collapsed ? (
              <span className="min-w-0 flex-1 leading-tight">
                <span className="block truncate text-sm font-medium">{session.me?.user.display_name}</span>
                <span className="block truncate text-[11px] text-faint">{session.me?.memberships.find((m) => m.organization_id === session.organizationId)?.organization_name ?? session.me?.user.email}</span>
              </span>
            ) : null}
          </button>
          {accountOpen ? (
            <div className="fade-up absolute bottom-full left-2 z-30 mb-1 w-60 rounded-lg border border-border bg-surface p-1 shadow-card">
              <div className="px-3 py-2 text-xs text-muted">{session.me?.user.email}</div>
              {(session.me?.memberships.length ?? 0) > 1 ? (
                <div className="px-2 pb-1">
                  <select className="w-full rounded-md border border-border bg-surface px-2 py-1 text-xs" value={session.organizationId ?? ""} onChange={(e) => session.setOrganization(e.target.value)} aria-label="Organization">
                    {session.me?.memberships.map((m) => <option key={m.organization_id} value={m.organization_id}>{m.organization_name} · {m.role}</option>)}
                  </select>
                </div>
              ) : null}
              <MenuItem icon={Settings} label="Account & appearance" onClick={() => { setAccountOpen(false); router.push("/app/account"); }} />
              {isAdmin ? <MenuItem icon={Shield} label="Admin console" onClick={() => { setAccountOpen(false); router.push("/admin"); }} /> : null}
              <MenuItem icon={Bot} label="Agents & commands" onClick={() => { setAccountOpen(false); router.push("/app/nodes"); }} />
              <MenuItem icon={Search} label="Search chats" onClick={() => { setAccountOpen(false); router.push("/app/history"); }} />
              <div className="my-1 border-t border-border" />
              <MenuItem icon={LogOut} label="Sign out" onClick={async () => { await session.logout(); router.replace("/login"); }} />
            </div>
          ) : null}
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">{children}</div>
    </div>
  );
}

function MenuItem({ icon: Icon, label, hint, onClick }: { icon: typeof Plus; label: string; hint?: string; onClick: () => void }) {
  return (
    <button onClick={onClick} className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm hover:bg-surface-2">
      <Icon size={15} className="text-muted" />
      <span className="flex-1">
        <span className="block">{label}</span>
        {hint ? <span className="block text-[11px] text-faint">{hint}</span> : null}
      </span>
    </button>
  );
}
