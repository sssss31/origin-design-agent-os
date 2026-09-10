"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useSession } from "@/lib/session";

const NAV = [
  ["/admin", "Dashboard"],
  ["/admin/agents", "Agents"],
  ["/admin/skills", "Skills"],
  ["/admin/providers", "Providers"],
  ["/admin/tools", "Tools"],
] as const;

export function AdminShell({ title, children }: { title: string; children: React.ReactNode }) {
  const session = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const allowed = session.status === "authenticated" && Boolean(session.me?.capabilities.admin_console);

  useEffect(() => {
    if (session.status === "anonymous") router.replace("/login");
    if (session.status === "authenticated" && !session.me?.capabilities.admin_console) router.replace("/app");
  }, [session, router]);

  if (!allowed) return <div className="flex min-h-screen items-center justify-center text-sm text-muted">Loading…</div>;
  return (
    <div className="flex min-h-screen">
      <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-surface p-3">
        <p className="px-2 text-sm font-semibold">Admin console</p>
        <p className="mb-4 px-2 text-[11px] text-muted">Runtime configuration</p>
        <nav className="space-y-0.5">
          {NAV.map(([href, label]) => {
            const active = href === "/admin" ? pathname === href : pathname.startsWith(href);
            return (
              <Link key={href} href={href} className={`block rounded-md px-2 py-1.5 text-sm ${active ? "bg-accent/15 text-accent" : "hover:bg-surface-2"}`}>
                {label}
              </Link>
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
