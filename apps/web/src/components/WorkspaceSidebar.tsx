"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { WORKSPACES_CHANGED, workspacesApi } from "@/lib/api/workspaces";
import { useSession } from "@/lib/session";
import type { WorkspaceOut } from "@/types/api";

export function WorkspaceSidebar() {
  const pathname = usePathname();
  const session = useSession();
  const [workspaces, setWorkspaces] = useState<WorkspaceOut[]>([]);

  useEffect(() => {
    if (session.status !== "authenticated") return;
    const refresh = () => workspacesApi.list().then(setWorkspaces).catch(() => setWorkspaces([]));
    void refresh();
    window.addEventListener(WORKSPACES_CHANGED, refresh);
    return () => window.removeEventListener(WORKSPACES_CHANGED, refresh);
  }, [session.status, session.organizationId]);

  const isAdmin = session.me?.capabilities.admin_console ?? false;
  const link = (href: string, label: string, exact = false) => {
    const active = exact ? pathname === href : pathname.startsWith(href);
    return (
      <Link
        key={href}
        href={href}
        className={`block rounded-md px-2 py-1.5 text-sm ${active ? "bg-accent/15 text-accent" : "text-text hover:bg-surface-2"}`}
      >
        {label}
      </Link>
    );
  };

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-surface p-3">
      <div className="mb-4 px-2">
        <p className="text-sm font-semibold">Origin</p>
        <p className="text-[11px] text-muted">Design Agent OS</p>
      </div>
      <nav className="space-y-0.5">
        {link("/app/workspaces", "Workspaces", true)}
      </nav>
      <p className="mt-4 mb-1 px-2 text-[11px] font-medium uppercase tracking-wide text-muted">Your workspaces</p>
      <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto">
        {workspaces.length === 0 ? <p className="px-2 text-xs text-muted">None yet</p> : null}
        {workspaces.map((ws) => link(`/app/workspaces/${ws.id}`, ws.name))}
      </div>
      {isAdmin ? <nav className="mt-4 border-t border-border pt-3">{link("/admin", "Admin console")}</nav> : null}
    </aside>
  );
}
