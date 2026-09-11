"use client";

import { Upload } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { ArtifactCard } from "@/components/chat/ArtifactCard";
import { PageHeader } from "@/components/shell/PageHeader";
import { Button } from "@/components/ui/Button";
import { Badge, Card, ErrorText } from "@/components/ui/Card";
import { Select } from "@/components/ui/JsonField";
import { assetsApi, resolveDownloadUrl } from "@/lib/api/chat";
import { dashboardApi } from "@/lib/api/dashboard";
import type { AssetOut } from "@/types/chat";
import type { LibraryOut } from "@/types/dashboard";

function Library() {
  const params = useSearchParams();
  const [tab, setTab] = useState<"artifacts" | "assets">(params.get("tab") === "assets" ? "assets" : "artifacts");
  const [projectId, setProjectId] = useState("");
  const [status, setStatus] = useState("");
  const [data, setData] = useState<LibraryOut | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState("image");
  const [uploadProject, setUploadProject] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(params.get("upload") === "1");
  const load = useCallback(() => dashboardApi.library({ project_id: projectId || undefined, artifact_status: status || undefined, limit: 120 }).then(setData).catch(() => setData({ artifacts: [], assets: [], projects: [] })), [projectId, status]);
  useEffect(() => {
    void load();
  }, [load]);
  const projects = data?.projects ?? [];
  return (
    <main className="flex-1 overflow-y-auto">
      <PageHeader
        title="Library"
        subtitle="Everything produced or uploaded across your projects — with versions, lineage and approval status."
        actions={<Button onClick={() => { setTab("assets"); setShowUpload(true); }}><Upload size={14} /> Upload asset</Button>}
      />
      <div className="px-8 pb-10">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <div className="flex rounded-lg border border-border bg-surface p-0.5">
            {(["artifacts", "assets"] as const).map((t) => (
              <button key={t} onClick={() => setTab(t)} className={`rounded-md px-3 py-1 text-xs font-medium capitalize ${tab === t ? "bg-accent-soft text-accent" : "text-muted hover:text-text"}`}>{t}</button>
            ))}
          </div>
          <div className="w-56"><Select value={projectId} onChange={setProjectId} options={[{ value: "", label: "All projects" }, ...projects.map((p) => ({ value: p.id, label: `${p.workspace_name} / ${p.name}` }))]} /></div>
          {tab === "artifacts" ? <div className="w-40"><Select value={status} onChange={setStatus} options={[{ value: "", label: "Any status" }, ...["generated", "qc_failed", "approved", "final", "archived"].map((s) => ({ value: s, label: s }))]} /></div> : null}
          <span className="ml-auto text-xs text-faint">{tab === "artifacts" ? data?.artifacts.length ?? 0 : data?.assets.length ?? 0} items</span>
        </div>

        {showUpload ? (
          <Card className="mb-4 flex flex-wrap items-end gap-3">
            <label className="text-xs text-muted">File<br /><input type="file" className="mt-1 text-xs" aria-label="Asset file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
            <div className="w-40"><Select label="Kind" value={kind} onChange={setKind} options={["logo", "image", "pdf", "brand_guide", "svg", "font", "reference", "other"].map((k) => ({ value: k, label: k }))} /></div>
            <div className="w-56"><Select label="Project" value={uploadProject} onChange={setUploadProject} options={[{ value: "", label: "Choose project…" }, ...projects.map((p) => ({ value: p.id, label: `${p.workspace_name} / ${p.name}` }))]} /></div>
            <Button disabled={!file || !uploadProject} onClick={async () => { if (!file) return; setError(null); try { await assetsApi.upload(uploadProject, file, { kind }); setFile(null); setShowUpload(false); await load(); } catch (err) { setError(err instanceof Error ? err.message : "Upload failed"); } }}>Upload</Button>
            <Button variant="ghost" onClick={() => setShowUpload(false)}>Cancel</Button>
            <ErrorText>{error}</ErrorText>
          </Card>
        ) : null}

        {data === null ? <p className="text-sm text-muted">Loading…</p> : null}
        {tab === "artifacts" ? (
          data && data.artifacts.length === 0 ? (
            <Empty text="No artifacts yet. Start a design run from Home or a project chat." />
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {data?.artifacts.map((a) => <ArtifactCard key={a.id} artifactId={a.id} initial={a} onChange={() => void load()} />)}
            </div>
          )
        ) : data && data.assets.length === 0 ? (
          <Empty text="No assets yet. Upload logos, images, PDFs, brand guides or fonts." />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{data?.assets.map((a) => <AssetTile key={a.id} asset={a} />)}</div>
        )}
      </div>
    </main>
  );
}

function AssetTile({ asset }: { asset: AssetOut }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (asset.current_version?.mime_type.startsWith("image/") && asset.current_version.mime_type !== "image/svg+xml") {
      assetsApi.download(asset.id).then((d) => setUrl(resolveDownloadUrl(d.url))).catch(() => setUrl(null));
    }
  }, [asset]);
  return (
    <div className="flex gap-3 rounded-card border border-border bg-surface p-2">
      {/* eslint-disable-next-line @next/next/no-img-element -- signed private URL */}
      {url ? <img src={url} alt={asset.name} className="h-24 w-24 shrink-0 rounded object-cover" /> : <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded bg-surface-2 text-[10px] text-muted">{asset.kind}</div>}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{asset.name}</p>
        <p className="text-[11px] text-muted">{asset.current_version?.mime_type}{asset.current_version?.width ? ` · ${asset.current_version.width}×${asset.current_version.height}` : ""} · v{asset.current_version?.version}</p>
        <div className="mt-1 flex items-center gap-1"><Badge>{asset.kind}</Badge><Button variant="ghost" className="px-2 py-0.5 text-[11px]" onClick={() => assetsApi.download(asset.id).then((d) => window.open(resolveDownloadUrl(d.url), "_blank"))}>Download</Button></div>
      </div>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="rounded-card border border-dashed border-border p-10 text-center text-sm text-muted">{text}</div>;
}

export default function LibraryPage() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-muted">Loading…</div>}>
      <Library />
    </Suspense>
  );
}
