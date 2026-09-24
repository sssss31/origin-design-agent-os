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
  { href: "/admin", label: "Overview" },
  {
    href: "/admin/agents",
    label: "Agents",
    children: [
      { href: "/admin/agents", label: "All agents" },
      { href: "/admin/agents/new", label: "Add agent" },
    ],
  },
  { href: "/admin/activity", label: "Activity" },
  { href: "/admin/users", label: "Users" },
  { href: "/admin/settings", label: "Settings" },
  { href: "/admin/audit", label: "Audit log" },
  {
    href: "/admin/skills",
    label: "Advanced",
    children: [
      { href: "/admin/skills", label: "Skills" },
      { href: "/admin/tools", label: "Tools" },
      { href: "/admin/providers", label: "AI providers" },
      { href: "/admin/integrations", label: "Custom integrations" },
      { href: "/admin/usage", label: "Usage & cost" },
    ],
  },
];

export function AdminShell({ title, children }: { title: string; children: React.ReactNode }) {
  const session = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const allowed = session.status === "authenticated" && Boolean(session.me?.capabilities.admin_console);
  const [open, setOpen] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (session.status === "anonymous") router.replace("/login");
    if (session.status === "authenticated" && !session.me?.capabilities.admin_console) router.replace("/");
  }, [session, router]);

  if (!allowed) return <div className="flex min-h-screen items-center justify-center text-sm text-muted">Loading…</div>;
  return (
    <div className="flex min-h-screen">
      <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-surface p-3">
        <p className="px-2 text-[11px] font-semibold uppercase tracking-wider text-faint">Admin</p>
        <p className="mb-3 px-2 text-sm font-semibold">Origin console</p>
        <nav className="space-y-0.5">
          {NAV.map((item) => {
            const active =
              item.href === "/admin"
                ? pathname === item.href
                : item.label === "Advanced"
                  ? ["/admin/skills", "/admin/tools", "/admin/providers", "/admin/integrations", "/admin/usage"].some((h) => pathname.startsWith(h))
                  : pathname.startsWith(item.href);
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
          <Link href="/" className="block rounded-md px-2 py-1.5 text-sm text-muted hover:bg-surface-2">← Back to chat</Link>
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
