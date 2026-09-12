import { api } from "@/lib/api/client";
import type { AgentGraph, LibraryOut, ProfileOut, QuickStartOut, RecentConversation, RecentRun } from "@/types/dashboard";

export const dashboardApi = {
  recents: (params: { limit?: number; search?: string; include_archived?: boolean } = {}) => {
    const q = new URLSearchParams();
    if (params.limit) q.set("limit", String(params.limit));
    if (params.search) q.set("search", params.search);
    if (params.include_archived) q.set("include_archived", "true");
    return api<RecentConversation[]>(`/conversations/recent?${q.toString()}`);
  },
  library: (params: { project_id?: string; artifact_status?: string; limit?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.project_id) q.set("project_id", params.project_id);
    if (params.artifact_status) q.set("artifact_status", params.artifact_status);
    if (params.limit) q.set("limit", String(params.limit));
    return api<LibraryOut>(`/library?${q.toString()}`);
  },
  graph: () => api<AgentGraph>("/agents/graph"),
  quickstart: (body: { content: string; project_id?: string; selected_asset_ids?: string[]; title?: string }) => api<QuickStartOut>("/quickstart", { method: "POST", body }),
  profile: () => api<ProfileOut>("/me/profile"),
  recentRuns: (limit = 20) => api<RecentRun[]>(`/runs/recent?limit=${limit}`),
};
