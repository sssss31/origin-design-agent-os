"use client";

import { Archive, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/shell/PageHeader";
import { Input } from "@/components/ui/Input";
import { dashboardApi } from "@/lib/api/dashboard";
import type { RecentConversation } from "@/types/dashboard";

export default function HistoryPage() {
  const [query, setQuery] = useState("");
  const [archived, setArchived] = useState(false);
  const [rows, setRows] = useState<RecentConversation[] | null>(null);
  useEffect(() => {
    const t = setTimeout(() => {
      dashboardApi.recents({ limit: 200, search: query || undefined, include_archived: archived }).then(setRows).catch(() => setRows([]));
    }, 200);
    return () => clearTimeout(t);
  }, [query, archived]);
  const groups = groupByDay(rows ?? []);
  return (
    <main className="flex-1 overflow-y-auto">
      <PageHeader title="Chat history" subtitle="Every conversation across your workspaces. Search titles and message content." />
      <div className="px-8 pb-10">
        <div className="mb-5 flex max-w-2xl items-center gap-2">
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
            <Input className="pl-8" placeholder="Search chats and messages" value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          <label className="flex items-center gap-1.5 text-xs text-muted"><input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} /> <Archive size={12} /> include archived</label>
        </div>
        {rows === null ? <p className="text-sm text-muted">Loading…</p> : rows.length === 0 ? <p className="text-sm text-muted">No conversations match.</p> : null}
        {groups.map(([day, items]) => (
          <section key={day} className="mb-6 max-w-2xl">
            <h2 className="mb-2 text-[11px] font-medium uppercase tracking-wider text-faint">{day}</h2>
            <ul className="divide-y divide-border rounded-card border border-border bg-surface">
              {items.map((c) => (
                <li key={c.id}>
                  <Link href={`/app/projects/${c.project_id}/chat/${c.id}`} className="block px-4 py-3 hover:bg-surface-2">
                    <div className="flex items-center justify-between gap-3">
                      <p className="truncate text-sm font-medium">{c.title}</p>
                      <span className="shrink-0 text-[11px] text-faint">{c.status === "archived" ? "archived · " : ""}{c.workspace_name} / {c.project_name}</span>
                    </div>
                    <p className="mt-0.5 truncate text-xs text-muted">{c.last_message_preview ?? "—"}</p>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </main>
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
