"use client";

import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { useSession } from "@/lib/session";

export function TopBar({ title }: { title?: string }) {
  const session = useSession();
  const router = useRouter();
  const memberships = session.me?.memberships ?? [];
  return (
    <header className="flex h-12 items-center justify-between border-b border-border bg-surface px-4">
      <h1 className="text-sm font-semibold">{title ?? ""}</h1>
      <div className="flex items-center gap-3">
        {memberships.length > 1 ? (
          <select
            className="rounded-md border border-border bg-surface px-2 py-1 text-xs"
            value={session.organizationId ?? ""}
            onChange={(e) => session.setOrganization(e.target.value)}
            aria-label="Organization"
          >
            {memberships.map((m) => (
              <option key={m.organization_id} value={m.organization_id}>
                {m.organization_name} · {m.role}
              </option>
            ))}
          </select>
        ) : memberships[0] ? (
          <span className="text-xs text-muted">
            {memberships[0].organization_name} · {memberships[0].role}
          </span>
        ) : null}
        <span className="text-xs text-muted">{session.me?.user.email}</span>
        <Button
          variant="secondary"
          onClick={async () => {
            await session.logout();
            router.replace("/login");
          }}
        >
          Sign out
        </Button>
      </div>
    </header>
  );
}
