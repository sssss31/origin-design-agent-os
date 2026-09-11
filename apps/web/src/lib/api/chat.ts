import { API_BASE, api } from "@/lib/api/client";
import { tokenStore } from "@/lib/token-store";
import type { ArtifactOut, AssetOut, ConversationOut, DownloadOut, EventOut, LineageNode, MessageOut, RunCreated, RunOut } from "@/types/chat";

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const token = tokenStore.getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const org = tokenStore.getOrganizationId();
  if (org) headers["X-Organization-Id"] = org;
  return headers;
}

export const conversationsApi = {
  list: (projectId: string, includeArchived = false) => api<ConversationOut[]>(`/projects/${projectId}/conversations?include_archived=${includeArchived}`),
  create: (projectId: string, title?: string) => api<ConversationOut>(`/projects/${projectId}/conversations`, { method: "POST", body: { title } }),
  get: (id: string) => api<ConversationOut>(`/conversations/${id}`),
  update: (id: string, body: { title?: string; status?: "active" | "archived" }) => api<ConversationOut>(`/conversations/${id}`, { method: "PATCH", body }),
  messages: (id: string) => api<MessageOut[]>(`/conversations/${id}/messages`),
  search: (projectId: string, q: string) => api<{ message: MessageOut; conversation_title: string }[]>(`/projects/${projectId}/messages/search?q=${encodeURIComponent(q)}`),
};

export const runsApi = {
  create: (conversationId: string, body: { content?: string; message_id?: string; command?: string; selected_asset_ids?: string[]; selected_artifact_ids?: string[]; options?: Record<string, unknown> }) =>
    api<RunCreated>(`/conversations/${conversationId}/runs`, { method: "POST", body }),
  list: (conversationId: string) => api<RunOut[]>(`/conversations/${conversationId}/runs`),
  get: (runId: string) => api<RunOut>(`/runs/${runId}`),
  history: (runId: string, after = 0) => api<EventOut[]>(`/runs/${runId}/events/history?after=${after}`),
  clarify: (runId: string, answer: string) => api<RunOut>(`/runs/${runId}/clarification`, { method: "POST", body: { answer } }),
  cancel: (runId: string) => api<RunOut>(`/runs/${runId}/cancel`, { method: "POST" }),
  retry: (runId: string) => api<RunOut>(`/runs/${runId}/retry`, { method: "POST" }),
};

export const assetsApi = {
  list: (projectId: string) => api<AssetOut[]>(`/projects/${projectId}/assets`),
  async upload(projectId: string, file: File, meta: { name?: string; kind?: string; description?: string } = {}): Promise<AssetOut> {
    const form = new FormData();
    form.append("file", file);
    if (meta.name) form.append("name", meta.name);
    if (meta.kind) form.append("kind", meta.kind);
    if (meta.description) form.append("description", meta.description);
    const res = await fetch(`${API_BASE}/projects/${projectId}/assets`, { method: "POST", headers: authHeaders(), body: form });
    const data = (await res.json()) as unknown;
    if (!res.ok) throw new Error((data as { error?: { message?: string } }).error?.message ?? "Upload failed");
    return data as AssetOut;
  },
  download: (assetId: string) => api<DownloadOut>(`/assets/${assetId}/download`),
};

export const artifactsApi = {
  list: (projectId: string) => api<ArtifactOut[]>(`/projects/${projectId}/artifacts`),
  get: (id: string) => api<ArtifactOut>(`/artifacts/${id}`),
  approve: (id: string) => api<ArtifactOut>(`/artifacts/${id}/approve`, { method: "POST" }),
  setStatus: (id: string, status: string) => api<ArtifactOut>(`/artifacts/${id}/status`, { method: "POST", body: { status } }),
  download: (id: string) => api<DownloadOut>(`/artifacts/${id}/download`),
  lineage: (id: string) => api<LineageNode>(`/artifacts/${id}/lineage`),
};

/** Absolute URL for a signed download returned by the API (local storage returns a relative path). */
export function resolveDownloadUrl(url: string): string {
  if (url.startsWith("http")) return url;
  if (url.startsWith("/api/v1/")) return API_BASE.startsWith("http") ? API_BASE.replace(/\/api\/v1$/, "") + url : url;
  return url;
}
