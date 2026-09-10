"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { WorkspaceSidebar } from "@/components/WorkspaceSidebar";
import { useSession } from "@/lib/session";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const session = useSession();
  const router = useRouter();

  useEffect(() => {
    if (session.status === "anonymous") router.replace("/login");
  }, [session.status, router]);

  if (session.status !== "authenticated") {
    return <div className="flex min-h-screen items-center justify-center text-sm text-muted">Loading…</div>;
  }
  return (
    <div className="flex min-h-screen">
      <WorkspaceSidebar />
      <div className="flex min-w-0 flex-1 flex-col">{children}</div>
    </div>
  );
}
