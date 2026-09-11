"use client";

import { Moon, Sun, SunMoon } from "lucide-react";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/shell/PageHeader";
import { Badge, Card, CardTitle } from "@/components/ui/Card";
import { dashboardApi } from "@/lib/api/dashboard";
import { useSession } from "@/lib/session";
import { applyTheme, readTheme, type ThemeChoice } from "@/lib/theme";
import type { ProfileOut } from "@/types/dashboard";

export default function AccountPage() {
  const session = useSession();
  const [profile, setProfile] = useState<ProfileOut | null>(null);
  const [theme, setTheme] = useState<ThemeChoice>("system");
  useEffect(() => {
    dashboardApi.profile().then(setProfile).catch(() => setProfile(null));
    // read the stored preference after hydration (localStorage is client-only)
    const id = requestAnimationFrame(() => setTheme(readTheme()));
    return () => cancelAnimationFrame(id);
  }, []);
  const choose = (t: ThemeChoice) => {
    setTheme(t);
    applyTheme(t);
  };
  return (
    <main className="flex-1 overflow-y-auto">
      <PageHeader title="Account" subtitle="Profile, organization and appearance." />
      <div className="grid max-w-4xl gap-4 px-8 pb-10 md:grid-cols-2">
        <Card>
          <CardTitle>Profile</CardTitle>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between"><dt className="text-muted">Name</dt><dd>{profile?.display_name ?? session.me?.user.display_name}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">Email</dt><dd>{profile?.email ?? session.me?.user.email}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">Organization</dt><dd>{profile?.organization_name ?? "—"} {profile?.role ? <Badge tone="accent">{profile.role}</Badge> : null}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">Member since</dt><dd>{profile ? new Date(profile.joined_at).toLocaleDateString() : "—"}</dd></div>
          </dl>
          {profile ? (
            <div className="mt-4 grid grid-cols-3 gap-2 text-center">
              {Object.entries(profile.counts).map(([k, v]) => (
                <div key={k} className="rounded-md bg-surface-2 p-2"><p className="text-lg font-semibold">{v}</p><p className="text-[11px] text-muted">{k}</p></div>
              ))}
            </div>
          ) : null}
        </Card>
        <Card>
          <CardTitle>Appearance</CardTitle>
          <div className="grid grid-cols-3 gap-2">
            {([["system", SunMoon, "System"], ["light", Sun, "Light"], ["dark", Moon, "Dark"]] as const).map(([id, Icon, label]) => (
              <button key={id} onClick={() => choose(id)} className={`flex flex-col items-center gap-1 rounded-card border p-3 text-xs ${theme === id ? "border-accent bg-accent-soft text-accent" : "border-border hover:bg-surface-2"}`}>
                <Icon size={18} /> {label}
              </button>
            ))}
          </div>
          <p className="mt-3 text-xs text-muted">Stored in this browser only.</p>
        </Card>
        <Card className="md:col-span-2">
          <CardTitle>Organizations</CardTitle>
          <ul className="divide-y divide-border text-sm">
            {session.me?.memberships.map((m) => (
              <li key={m.organization_id} className="flex items-center justify-between py-2">
                <span>{m.organization_name} <span className="text-xs text-muted">{m.organization_slug}</span></span>
                <span className="flex items-center gap-2"><Badge>{m.role}</Badge>{m.organization_id === session.organizationId ? <Badge tone="success">active</Badge> : <button className="text-xs text-accent" onClick={() => session.setOrganization(m.organization_id)}>switch</button>}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </main>
  );
}
