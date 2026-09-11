"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Card";
import { artifactsApi, resolveDownloadUrl } from "@/lib/api/chat";
import type { ArtifactOut } from "@/types/chat";

const tone: Record<ArtifactOut["status"], "neutral" | "accent" | "success" | "warning" | "danger"> = { draft: "neutral", generated: "accent", qc_failed: "danger", approved: "success", final: "success", archived: "neutral" };

export function ArtifactCard({ artifactId, initial, onChange, compact = false }: { artifactId: string; initial?: ArtifactOut; onChange?: (a: ArtifactOut) => void; compact?: boolean }) {
  const [artifact, setArtifact] = useState<ArtifactOut | null>(initial ?? null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!initial) artifactsApi.get(artifactId).then(setArtifact).catch(() => setArtifact(null));
  }, [artifactId, initial]);
  useEffect(() => {
    if (artifact?.current_version?.mime_type.startsWith("image/") && artifact.current_version.mime_type !== "image/svg+xml") {
      artifactsApi.download(artifactId).then((d) => setPreviewUrl(resolveDownloadUrl(d.url))).catch(() => setPreviewUrl(null));
    }
  }, [artifact, artifactId]);
  if (!artifact) return <div className="rounded-md border border-border p-2 text-xs text-muted">artifact {artifactId.slice(0, 8)}…</div>;
  const v = artifact.current_version;
  const act = async (fn: () => Promise<ArtifactOut>) => {
    setBusy(true);
    try {
      const updated = await fn();
      setArtifact(updated);
      onChange?.(updated);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className={`flex gap-3 rounded-md border border-border bg-surface p-2 ${compact ? "" : "max-w-md"}`}>
      {/* eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL from a private bucket; the Next image optimizer cannot fetch it */}
      {previewUrl ? <img src={previewUrl} alt={artifact.name} className={`${compact ? "h-16 w-16" : "h-24 w-24"} shrink-0 rounded object-cover`} /> : <div className={`${compact ? "h-16 w-16" : "h-24 w-24"} shrink-0 rounded bg-surface-2 text-center text-[10px] leading-[4rem] text-muted`}>{artifact.type}</div>}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{artifact.name}</p>
        <p className="text-[11px] text-muted">
          v{v?.version_number ?? "?"}{v?.width ? ` · ${v.width}×${v.height}` : ""}{v ? ` · ${(v.size_bytes / 1024).toFixed(0)} KB` : ""}{artifact.producer_agent_slug ? ` · by ${artifact.producer_agent_slug}` : ""}
        </p>
        <div className="mt-1 flex flex-wrap items-center gap-1">
          <Badge tone={tone[artifact.status]}>{artifact.status}</Badge>
          <Button variant="ghost" className="px-2 py-0.5 text-[11px]" onClick={() => artifactsApi.download(artifactId).then((d) => window.open(resolveDownloadUrl(d.url), "_blank"))}>Download</Button>
          {artifact.status === "generated" ? <Button variant="ghost" className="px-2 py-0.5 text-[11px]" disabled={busy} onClick={() => act(() => artifactsApi.approve(artifactId))}>Approve</Button> : null}
          {artifact.status === "approved" ? <Button variant="ghost" className="px-2 py-0.5 text-[11px]" disabled={busy} onClick={() => act(() => artifactsApi.setStatus(artifactId, "final"))}>Mark final</Button> : null}
        </div>
      </div>
    </div>
  );
}
