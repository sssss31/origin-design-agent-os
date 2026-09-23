import { api } from "@/lib/api/client";
import type { WorkItem } from "@/types/work";

export const workApi = {
  list: (params: { search?: string; agent_id?: string; date_from?: string; date_to?: string } = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v) q.set(k, v); });
    return api<WorkItem[]>(`/work?${q.toString()}`);
  },
  get: (conversationId: string) => api<WorkItem>(`/work/${conversationId}`),
};
