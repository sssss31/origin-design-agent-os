"use client";

import { useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/AdminShell";
import { Card, EmptyState } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { api } from "@/lib/api/client";

interface AuditRow {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  actor_email: string | null;
  before_json: Record<string, unknown> | null;
  after_json: Record<string, unknown> | null;
  request_id: string | null;
  ip_address: string | null;
  created_at: string;
}

export default function AuditPage() {
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    api<AuditRow[]>(`/admin/audit?limit=200${filter ? `&action=${encodeURIComponent(filter)}` : ""}`).then(setRows).catch(() => setRows([]));
  }, [filter]);
  return (
    <AdminShell title="Audit log">
      <div className="mb-3 max-w-sm"><Input placeholder="Filter by action prefix, e.g. agent. or provider.secret" value={filter} onChange={(e) => setFilter(e.target.value)} /></div>
      {rows === null ? <p className="text-sm text-muted">Loading…</p> : rows.length === 0 ? <EmptyState title="No audit entries" /> : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-xs">
            <thead className="bg-surface-2 text-left text-muted"><tr><th className="p-2">When</th><th className="p-2">Who</th><th className="p-2">Action</th><th className="p-2">Entity</th><th className="p-2">Request</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <>
                  <tr key={r.id} className="cursor-pointer border-t border-border hover:bg-surface-2" onClick={() => setOpen(open === r.id ? null : r.id)}>
                    <td className="p-2 whitespace-nowrap">{new Date(r.created_at).toLocaleString()}</td>
                    <td className="p-2">{r.actor_email ?? "system"}</td>
                    <td className="p-2 font-mono">{r.action}</td>
                    <td className="p-2">{r.entity_type} <span className="text-muted">{r.entity_id?.slice(0, 8)}</span></td>
                    <td className="p-2 text-muted">{r.request_id?.slice(0, 8)}{r.ip_address ? ` · ${r.ip_address}` : ""}</td>
                  </tr>
                  {open === r.id ? (
                    <tr key={r.id + "-detail"} className="border-t border-border bg-surface-2">
                      <td colSpan={5} className="p-2">
                        <div className="grid gap-2 md:grid-cols-2">
                          <pre className="overflow-x-auto rounded bg-surface p-2 text-[10px]">before: {JSON.stringify(r.before_json, null, 1)}</pre>
                          <pre className="overflow-x-auto rounded bg-surface p-2 text-[10px]">after: {JSON.stringify(r.after_json, null, 1)}</pre>
                        </div>
                      </td>
                    </tr>
                  ) : null}
                </>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </AdminShell>
  );
}
