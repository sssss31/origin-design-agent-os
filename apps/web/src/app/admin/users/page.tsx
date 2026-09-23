"use client";

import { useCallback, useEffect, useState } from "react";
import { AdminShell, useAsyncAction } from "@/components/admin/AdminShell";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardTitle, ErrorText } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/JsonField";
import { api } from "@/lib/api/client";
import { useSession } from "@/lib/session";

interface Member { user_id: string; email: string; display_name: string; role: "admin" | "member" | "viewer"; is_active: boolean; last_login_at: string | null; joined_at: string; requests_30d: number; cost_30d_usd: number }

export default function UsersPage() {
  const session = useSession();
  const run = useAsyncAction();
  const [members, setMembers] = useState<Member[] | null>(null);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("member");
  const [tempPassword, setTempPassword] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api<Member[]>("/admin/users").then(setMembers).catch(() => setMembers([])), []);
  useEffect(() => { void load(); }, [load]);
  return (
    <AdminShell title="Users">
      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-xs">
            <thead className="bg-surface-2 text-left text-muted"><tr><th className="p-2">User</th><th className="p-2">Role</th><th className="p-2">Status</th><th className="p-2">Last login</th><th className="p-2 text-right">Requests 30d</th><th className="p-2 text-right">Cost 30d</th><th className="p-2"></th></tr></thead>
            <tbody>
              {(members ?? []).map((m) => (
                <tr key={m.user_id} className="border-t border-border">
                  <td className="p-2"><span className="font-medium">{m.display_name}</span><span className="block text-muted">{m.email}</span></td>
                  <td className="p-2"><Select value={m.role} onChange={(r) => void run(async () => { await api(`/admin/users/${m.user_id}`, { method: "PATCH", body: { role: r } }); await load(); }, setError)} options={[{ value: "admin", label: "admin" }, { value: "member", label: "member" }, { value: "viewer", label: "viewer" }]} /></td>
                  <td className="p-2"><Badge tone={m.is_active ? "success" : "neutral"}>{m.is_active ? "active" : "deactivated"}</Badge></td>
                  <td className="p-2">{m.last_login_at ? new Date(m.last_login_at).toLocaleString() : "never"}</td>
                  <td className="p-2 text-right">{m.requests_30d}</td>
                  <td className="p-2 text-right">${m.cost_30d_usd.toFixed(4)}</td>
                  <td className="p-2 text-right">{m.user_id !== session.me?.user.id ? <Button variant="ghost" onClick={() => void run(async () => { await api(`/admin/users/${m.user_id}`, { method: "PATCH", body: { is_active: !m.is_active } }); await load(); }, setError)}>{m.is_active ? "Deactivate" : "Reactivate"}</Button> : <span className="text-faint">you</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {members === null ? <p className="p-3 text-sm text-muted">Loading…</p> : null}
        </Card>
        <Card className="space-y-3">
          <CardTitle>Add user</CardTitle>
          <p className="text-[11px] text-muted">Members can run agents; viewers only read; admins manage this console. Provider credentials are never visible to non-admins.</p>
          <Field label="Email"><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          <Field label="Display name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Select label="Role" value={role} onChange={setRole} options={[{ value: "member", label: "member" }, { value: "viewer", label: "viewer" }, { value: "admin", label: "admin" }]} />
          <Button disabled={!email} onClick={() => void run(async () => { const r = await api<{ temporary_password: string | null }>("/admin/users", { method: "POST", body: { email, display_name: name || undefined, role } }); setTempPassword(r.temporary_password); setEmail(""); setName(""); await load(); }, setError)}>Add</Button>
          {tempPassword ? <p className="rounded-md bg-warning/10 p-2 text-xs">Temporary password (shown once): <code className="font-mono">{tempPassword}</code></p> : null}
          <ErrorText>{error}</ErrorText>
        </Card>
      </div>
    </AdminShell>
  );
}
