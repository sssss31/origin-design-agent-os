"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { dashboardApi } from "@/lib/api/dashboard";

/** "Chat" in the sidebar opens the most recent conversation, or the home composer when there is none. */
export default function ChatEntry() {
  const router = useRouter();
  useEffect(() => {
    dashboardApi
      .recents({ limit: 1 })
      .then((list) => {
        const c = list[0];
        router.replace(c ? `/app/projects/${c.project_id}/chat/${c.id}` : "/app?compose=1");
      })
      .catch(() => router.replace("/app?compose=1"));
  }, [router]);
  return <div className="p-8 text-sm text-muted">Opening your latest chat…</div>;
}
