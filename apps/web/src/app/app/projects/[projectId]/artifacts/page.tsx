"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArtifactCard } from "@/components/chat/ArtifactCard";
import { TopBar } from "@/components/TopBar";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle, EmptyState } from "@/components/ui/Card";
import { Select } from "@/components/ui/JsonField";
import { artifactsApi } from "@/lib/api/chat";
import type { ArtifactOut, LineageNode } from "@/types/chat";

function Tree({ node, depth = 0 }: { node: LineageNode; depth?: number }) {
  return (
    <div style={{ marginLeft: depth * 16 }} className="space-y-1">
      <ArtifactCard artifactId={node.artifact.id} initial={node.artifact} compact />
      {node.children.map((c) => <Tree key={c.artifact.id} node={c} depth={depth + 1} />)}
    </div>
  );
}

export default function ArtifactsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [artifacts, setArtifacts] = useState<ArtifactOut[] | null>(null);
  const [status, setStatus] = useState("all");
  const [lineage, setLineage] = useState<LineageNode | null>(null);
  const load = useCallback(() => artifactsApi.list(projectId).then(setArtifacts).catch(() => setArtifacts([])), [projectId]);
  useEffect(() => { void load(); }, [load]);
  const visible = (artifacts ?? []).filter((a) => status === "all" || a.status === status);
  return (
    <>
      <TopBar title="Artifacts" />
      <main className="grid flex-1 gap-4 p-4 lg:grid-cols-[1fr_380px]">
        <section className="space-y-2">
          <div className="flex items-center gap-2 text-xs text-muted">
            <Link href={`/app/projects/${projectId}`} className="text-accent">← project</Link>
            <span>Outputs produced by agents, versioned with lineage to the run and producing agent version.</span>
            <div className="ml-auto w-40"><Select value={status} onChange={setStatus} options={["all", "generated", "qc_failed", "approved", "final", "archived"].map((s) => ({ value: s, label: s }))} /></div>
          </div>
          {artifacts === null ? <p className="text-sm text-muted">Loading…</p> : null}
          {artifacts?.length === 0 ? <EmptyState title="No artifacts yet" body="Run /master, /resize or /auto in a chat to produce files." /> : null}
          {visible.map((a) => (
            <div key={a.id} className="flex items-center gap-2">
              <div className="flex-1"><ArtifactCard artifactId={a.id} initial={a} onChange={() => void load()} /></div>
              <Button variant="ghost" onClick={() => artifactsApi.lineage(a.id).then(setLineage)}>Lineage</Button>
            </div>
          ))}
        </section>
        <aside>
          <Card>
            <CardTitle>Lineage</CardTitle>
            {lineage ? <Tree node={lineage} /> : <p className="text-xs text-muted">Select “Lineage” on an artifact to see its parent and derived versions (master → resize → export).</p>}
          </Card>
        </aside>
      </main>
    </>
  );
}
