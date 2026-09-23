"use client";

import { ChevronDown } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useSession } from "@/lib/session";

interface NavItem {
  href: string;
  label: string;
  children?: { href: string; label: string }[];
}

/** Spec §18 navigation. Sub-items deep-link into the parent page. */
const NAV: NavItem[] = [
  { href: "/admin", label: "Dashboard" },
  {
    href: "/admin/agents",
    label: "Agents",
    children: [
      { href: "/admin/agents", label: "All Agents" },
      { href: "/admin/agents?new=1", label: "Create Agent" },
      { href: "/admin/agents?view=versions", label: "Agent Versions" },
    ],
  },
  { href: "/admin/skills", label: "Skills", children: [{ href: "/admin/skills", label: "All Skills" }, { href: "/admin/skills?new=1", label: "Create Skill" }] },
  { href: "/admin/tools", label: "Tools", children: [{ href: "/admin/tools", label: "All Tools" }, { href: "/admin/tools?new=1", label: "Create Tool" }] },
  {
    href: "/admin/integrations",
    label: "API Integrations",
    children: [
      { href: "/admin/integrations#openai", label: "OpenAI" },
      { href: "/admin/integrations#custom", label: "Custom APIs" },
      { href: "/admin/integrations?add=1", label: "Add Integration" },
    ],
  },
  { href: "/admin/usage", label: "Usage & Cost" },
  { href: "/admin/users", label: "Users" },
  { href: "/admin/settings", label: "System Settings" },
  { href: "/admin/audit", label: "Audit" },
];

export function AdminShell({ title, children }: { title: string; children: React.ReactNode }) {
  const session = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const allowed = session.status === "authenticated" && Boolean(session.me?.capabilities.admin_console);
  const [open, setOpen] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (session.status === "anonymous") router.replace("/login");
    if (session.status === "authenticated" && !session.me?.capabilities.admin_console) router.replace("/app");
  }, [session, router]);

  if (!allowed) return <div className="flex min-h-screen items-center justify-center text-sm text-muted">Loading…</div>;
  return (
    <div className="flex min-h-screen">
      <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-surface p-3">
        <p className="px-2 text-[11px] font-semibold uppercase tracking-wider text-faint">Admin</p>
        <p className="mb-3 px-2 text-sm font-semibold">Origin console</p>
        <nav className="space-y-0.5">
          {NAV.map((item) => {
            const active = item.href === "/admin" ? pathname === item.href : pathname.startsWith(item.href);
            const expanded = open[item.href] ?? active;
            return (
              <div key={item.href}>
                <div className={`flex items-center rounded-md ${active ? "bg-accent/15 text-accent" : "hover:bg-surface-2"}`}>
                  <Link href={item.href} className="flex-1 px-2 py-1.5 text-sm">{item.label}</Link>
                  {item.children ? (
                    <button aria-label={`Toggle ${item.label}`} onClick={() => setOpen((o) => ({ ...o, [item.href]: !expanded }))} className="px-2 text-faint">
                      <ChevronDown size={14} className={`transition ${expanded ? "rotate-180" : ""}`} />
                    </button>
                  ) : null}
                </div>
                {item.children && expanded ? (
                  <ul className="ml-3 border-l border-border pl-2">
                    {item.children.map((c) => (
                      <li key={c.href}>
                        <Link href={c.href} className="block rounded-md px-2 py-1 text-xs text-muted hover:bg-surface-2 hover:text-text">{c.label}</Link>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            );
          })}
        </nav>
        <div className="mt-auto border-t border-border pt-3">
          <Link href="/app" className="block rounded-md px-2 py-1.5 text-sm text-muted hover:bg-surface-2">← Back to app</Link>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 items-center justify-between border-b border-border bg-surface px-4">
          <h1 className="text-sm font-semibold">{title}</h1>
          <span className="text-xs text-muted">{session.me?.user.email}</span>
        </header>
        <main className="flex-1 p-4">{children}</main>
      </div>
    </div>
  );
}

export function useAsyncAction() {
  return async function run<T>(fn: () => Promise<T>, setError: (m: string | null) => void): Promise<T | undefined> {
    setError(null);
    try {
      return await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
      return undefined;
    }
  };
}
