"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** Providers moved to Admin → API Integrations. */
export default function ProvidersRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/admin/integrations");
  }, [router]);
  return <div className="p-8 text-sm text-muted">Redirecting to API Integrations…</div>;
}
