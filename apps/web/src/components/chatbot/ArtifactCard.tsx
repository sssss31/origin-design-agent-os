"use client";

import { Download, ExternalLink, FileText } from "lucide-react";
import { useEffect, useState } from "react";
import { artifactsApi, assetsApi, resolveDownloadUrl } from "@/lib/api/chat";
import type { AttachmentOut } from "@/types/chat";

const IMAGE_RE = /^image\/(png|jpe?g|webp|gif|svg\+xml)$/;

/**
 * What the user attached: images as a thumbnail (signed, short-lived URL), anything else as a chip.
 * `localUrl` is the browser's own copy, shown until the server copy is known.
 */
export function AttachmentThumb({ attachment, localUrl }: { attachment: AttachmentOut; localUrl?: string | null }) {
  const [url, setUrl] = useState<string | null>(localUrl ?? null);
  const id = attachment.asset_id;
  const isImage = IMAGE_RE.test(attachment.mime_type ?? "");
  useEffect(() => {
    if (!id || !isImage) return;
    assetsApi
      .download(id)
      .then((d) => setUrl(resolveDownloadUrl(d.url)))
      .catch(() => undefined);
  }, [id, isImage]);
  const name = attachment.name ?? "file";
  if ((isImage || localUrl) && url) {
    return (
      <a href={url} target="_blank" rel="noreferrer noopener" className="block overflow-hidden rounded-lg border border-border bg-surface" title={name}>
        {/* eslint-disable-next-line @next/next/no-img-element -- signed, short-lived URLs from the API */}
        <img src={url} alt={name} className="block max-h-48 max-w-[240px] object-cover" />
      </a>
    );
  }
  return <span className="flex items-center gap-1 rounded-full bg-surface px-2 py-0.5 text-[11px] text-muted"><FileText size={10} /> {name}</span>;
}

/** An image the agent is still rendering: the latest partial frame, dimmed until the final arrives. */
export function PreviewImage({ url, final }: { url: string; final: boolean }) {
  return (
    <div className="relative mt-2 max-w-md overflow-hidden rounded-xl border border-border bg-surface-2">
      {/* eslint-disable-next-line @next/next/no-img-element -- signed, short-lived URLs from the API */}
      <img src={url} alt="Image being generated" className={`block max-h-96 w-full object-contain transition-opacity duration-500 ${final ? "opacity-100" : "opacity-80"}`} />
      {!final ? <span className="absolute bottom-2 left-2 flex items-center gap-1.5 rounded-full bg-bg/80 px-2 py-0.5 text-[11px] text-muted"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" /> Generating image…</span> : null}
    </div>
  );
}

function formatSize(bytes?: number | null): string {
  if (!bytes) return "";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * A file the agent produced (brief §11): images preview inline, everything else is a file card.
 * The URL is a short-lived signed download link fetched from the API; unknown types are never
 * rendered as text.
 */
export function ArtifactCard({ attachment }: { attachment: AttachmentOut }) {
  const [url, setUrl] = useState<string | null>(null);
  const [mime, setMime] = useState<string>(attachment.mime_type ?? "");
  const [name, setName] = useState<string>(attachment.name ?? "file");
  const [failed, setFailed] = useState(false);
  const id = attachment.artifact_id;
  useEffect(() => {
    if (!id) return;
    artifactsApi
      .download(id)
      .then((d) => {
        setUrl(d.url);
        if (d.mime_type) setMime(d.mime_type);
        if (d.filename) setName(d.filename);
      })
      .catch(() => setFailed(true));
  }, [id]);
  const isImage = IMAGE_RE.test(mime);
  if (failed) return <p className="text-xs text-danger">Could not load {name}.</p>;
  return (
    <div className="mt-2 max-w-md overflow-hidden rounded-xl border border-border bg-surface">
      {isImage && url ? (
        <a href={url} target="_blank" rel="noreferrer noopener">
          {/* eslint-disable-next-line @next/next/no-img-element -- signed, short-lived URLs from the API */}
          <img src={url} alt={name} className="block max-h-96 w-full object-contain bg-surface-2" />
        </a>
      ) : null}
      <div className="flex items-center gap-3 px-3 py-2">
        <FileText size={18} className="shrink-0 text-muted" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{name}</p>
          <p className="text-[11px] text-faint">{mime || "file"}{formatSize(attachment.size)}</p>
        </div>
        {url ? (
          <>
            <a href={url} target="_blank" rel="noreferrer noopener" className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-text" aria-label="Open"><ExternalLink size={14} /></a>
            <a href={url} download={name} className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-text" aria-label="Download"><Download size={14} /></a>
          </>
        ) : (
          <span className="text-[11px] text-faint">loading…</span>
        )}
      </div>
    </div>
  );
}
