"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Button } from "@/components/ui/Button";
import { Badge, Card, CardTitle, EmptyState, ErrorText } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/JsonField";
import { assetsApi, resolveDownloadUrl } from "@/lib/api/chat";
import type { AssetOut } from "@/types/chat";

export default function AssetsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [assets, setAssets] = useState<AssetOut[] | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState("image");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => assetsApi.list(projectId).then(setAssets).catch(() => setAssets([])), [projectId]);
  useEffect(() => { void load(); }, [load]);
  return (
    <>
      <TopBar title="Assets" />
      <main className="grid flex-1 gap-4 p-4 lg:grid-cols-[1fr_320px]">
        <section className="space-y-2">
          <p className="text-xs text-muted"><Link href={`/app/projects/${projectId}`} className="text-accent">← project</Link> · Inputs and references used by the agents. Uploads are validated (type, size) and stored privately; downloads use short-lived signed links.</p>
          {assets === null ? <p className="text-sm text-muted">Loading…</p> : null}
          {assets?.length === 0 ? <EmptyState title="No assets yet" body="Upload logos, images, PDFs, brand guides or fonts." /> : null}
          {assets?.map((a) => (
            <Card key={a.id} className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{a.name} <Badge>{a.kind}</Badge> <Badge tone={a.status === "ready" ? "success" : "warning"}>{a.status}</Badge></p>
                <p className="text-xs text-muted">{a.current_version?.mime_type}{a.current_version?.width ? ` · ${a.current_version.width}×${a.current_version.height}` : ""} · v{a.current_version?.version} · {((a.current_version?.size_bytes ?? 0) / 1024).toFixed(0)} KB{a.description ? ` · ${a.description}` : ""}</p>
              </div>
              <Button variant="secondary" onClick={() => assetsApi.download(a.id).then((d) => window.open(resolveDownloadUrl(d.url), "_blank"))}>Download</Button>
            </Card>
          ))}
        </section>
        <aside>
          <Card className="space-y-3">
            <CardTitle>Upload asset</CardTitle>
            <input type="file" className="text-xs" aria-label="Asset file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <Select label="Kind" value={kind} onChange={setKind} options={["logo", "image", "pdf", "brand_guide", "svg", "font", "reference", "other"].map((k) => ({ value: k, label: k }))} />
            <Field label="Description"><Input value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
            <ErrorText>{error}</ErrorText>
            <Button disabled={!file || busy} onClick={async () => { if (!file) return; setBusy(true); setError(null); try { await assetsApi.upload(projectId, file, { kind, description: description || undefined }); setFile(null); setDescription(""); await load(); } catch (err) { setError(err instanceof Error ? err.message : "Upload failed"); } finally { setBusy(false); } }}>{busy ? "Uploading…" : "Upload"}</Button>
          </Card>
        </aside>
      </main>
    </>
  );
}
