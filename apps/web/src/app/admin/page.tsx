"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Card, CardTitle, EmptyState } from "@/components/ui/Card";
import { useSession } from "@/lib/session";

export default function AdminHome() {
  const session = useSession();
  const router = useRouter();
  useEffect(() => {
    if (session.status === "anonymous") router.replace("/login");
    if (session.status === "authenticated" && !session.me?.capabilities.admin_console) router.replace("/app");
  }, [session, router]);
  if (session.status !== "authenticated" || !session.me?.capabilities.admin_console) return null;
  return (
    <main className="mx-auto max-w-3xl space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Admin console</h1>
        <Link href="/app" className="text-xs text-accent">← back to app</Link>
      </div>
      <Card>
        <CardTitle>Agents · Skills · Providers · Tools · Audit</CardTitle>
        <EmptyState
          title="Configuration screens arrive in Phase 2"
          body="Agents, skills, providers, tools and handoffs are database entities managed here without redeploying."
        />
      </Card>
    </main>
  );
}
