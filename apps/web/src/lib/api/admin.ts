import { API_BASE, api } from "@/lib/api/client";
import { tokenStore } from "@/lib/token-store";
import type {
  AgentOut,
  AgentSummaryOut,
  AgentTestOut,
  AgentVersionInput,
  CommandOut,
  ModelCapabilities,
  ProviderConnectionOut,
  ProviderOut,
  ProviderStatusOut,
  ProviderTestOut,
  SkillOut,
  SkillVersionInput,
  ToolOut,
} from "@/types/admin";

const A = "/admin";

export const providersApi = {
  list: () => api<ProviderOut[]>(`${A}/providers`),
  create: (body: { name: string; type: string; base_url?: string; default_model?: string; environment?: string }) =>
    api<ProviderOut>(`${A}/providers`, { method: "POST", body }),
  update: (id: string, body: Partial<Pick<ProviderOut, "name" | "base_url" | "default_model" | "enabled" | "environment" | "rate_limit_policy">>) =>
    api<ProviderOut>(`${A}/providers/${id}`, { method: "PATCH", body }),
  setSecret: (id: string, api_key: string) => api<ProviderOut>(`${A}/providers/${id}/secret`, { method: "POST", body: { api_key } }),
  test: (id: string) => api<ProviderTestOut>(`${A}/providers/${id}/test`, { method: "POST" }),
  status: (type: string) => api<ProviderStatusOut>(`${A}/providers/${type}/status`),
  connectionTest: (ref: string) => api<ProviderConnectionOut>(`${A}/providers/${ref}/connection-test`, { method: "POST" }),
  deleteSecret: (id: string) => api<ProviderOut>(`${A}/providers/${id}/secret`, { method: "DELETE" }),
  remove: (id: string) => api<void>(`${A}/providers/${id}`, { method: "DELETE" }),
  supportedModels: (id: string) => api<{ model: string; display_name: string; capabilities: ModelCapabilities }[]>(`${A}/providers/${id}/supported-models`),
  setModels: (id: string, models: { model: string; enabled?: boolean }[], default_model: string | null) =>
    api<ProviderOut>(`${A}/providers/${id}/models`, { method: "PUT", body: { models, default_model } }),
};

export const toolsApi = {
  list: () => api<ToolOut[]>(`${A}/tools`),
  create: (body: Record<string, unknown>) => api<ToolOut>(`${A}/tools`, { method: "POST", body }),
  update: (id: string, body: Record<string, unknown>) => api<ToolOut>(`${A}/tools/${id}`, { method: "PATCH", body }),
  setSecret: (id: string, secret: string) => api<ToolOut>(`${A}/tools/${id}/secret`, { method: "POST", body: { secret } }),
  setPermission: (id: string, body: { subject_type: "role" | "workspace"; subject_key: string; allowed: boolean }) =>
    api<ToolOut>(`${A}/tools/${id}/permissions`, { method: "POST", body }),
  deletePermission: (id: string, permissionId: string) => api<ToolOut>(`${A}/tools/${id}/permissions/${permissionId}`, { method: "DELETE" }),
};

export const skillsApi = {
  list: () => api<SkillOut[]>(`${A}/skills`),
  get: (id: string) => api<SkillOut>(`${A}/skills/${id}`),
  create: (body: { name: string; description?: string; scope?: string; version?: SkillVersionInput }) =>
    api<SkillOut>(`${A}/skills`, { method: "POST", body }),
  update: (id: string, body: Partial<Pick<SkillOut, "name" | "description" | "scope" | "status">>) =>
    api<SkillOut>(`${A}/skills/${id}`, { method: "PATCH", body }),
  saveDraft: (id: string, body: SkillVersionInput) => api<SkillOut>(`${A}/skills/${id}/versions`, { method: "POST", body }),
  publish: (id: string, body: { version_id?: string; change_note?: string } = {}) =>
    api<SkillOut>(`${A}/skills/${id}/publish`, { method: "POST", body }),
  test: (id: string, body: { agent_id: string; input: string; use_draft?: boolean; variables?: Record<string, unknown> }) =>
    api<AgentTestOut>(`${A}/skills/${id}/test`, { method: "POST", body }),
  async uploadFile(id: string, file: File, description?: string): Promise<SkillOut> {
    const form = new FormData();
    form.append("file", file);
    if (description) form.append("description", description);
    const headers: Record<string, string> = {};
    const token = tokenStore.getAccessToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    const org = tokenStore.getOrganizationId();
    if (org) headers["X-Organization-Id"] = org;
    const res = await fetch(`${API_BASE}${A}/skills/${id}/files`, { method: "POST", headers, body: form });
    const data = (await res.json()) as unknown;
    if (!res.ok) throw new Error((data as { error?: { message?: string } }).error?.message ?? "Upload failed");
    return data as SkillOut;
  },
};

export const agentsApi = {
  list: () => api<AgentSummaryOut[]>(`${A}/agents`),
  get: (id: string) => api<AgentOut>(`${A}/agents/${id}`),
  create: (body: { name: string; command: string; description?: string; is_manager?: boolean; version?: AgentVersionInput }) =>
    api<AgentOut>(`${A}/agents`, { method: "POST", body }),
  update: (id: string, body: Partial<Pick<AgentOut, "name" | "command" | "description" | "is_manager" | "status">>) =>
    api<AgentOut>(`${A}/agents/${id}`, { method: "PATCH", body }),
  saveDraft: (id: string, body: AgentVersionInput) => api<AgentOut>(`${A}/agents/${id}/versions`, { method: "POST", body }),
  publish: (id: string, body: { version_id?: string; change_note?: string } = {}) =>
    api<AgentOut>(`${A}/agents/${id}/publish`, { method: "POST", body }),
  test: (id: string, body: { input: string; use_draft: boolean; project_id?: string }) =>
    api<AgentTestOut>(`${A}/agents/${id}/test`, { method: "POST", body }),
  reorderSkills: (id: string, skill_ids: string[]) => api<AgentOut>(`${A}/agents/${id}/skills/order`, { method: "PUT", body: { skill_ids } }),
  attachSkill: (id: string, skillId: string, body: { priority?: number; skill_version_id?: string | null; variables?: Record<string, unknown>; enabled?: boolean }) =>
    api<AgentOut>(`${A}/agents/${id}/skills/${skillId}`, { method: "POST", body }),
  detachSkill: (id: string, skillId: string) => api<AgentOut>(`${A}/agents/${id}/skills/${skillId}`, { method: "DELETE" }),
  attachTool: (id: string, toolId: string, body: { max_calls_per_run?: number | null; enabled?: boolean }) =>
    api<AgentOut>(`${A}/agents/${id}/tools/${toolId}`, { method: "POST", body }),
  detachTool: (id: string, toolId: string) => api<AgentOut>(`${A}/agents/${id}/tools/${toolId}`, { method: "DELETE" }),
  addHandoff: (id: string, targetId: string, body: { routing_hint: string; is_failure_route: boolean }) =>
    api<AgentOut>(`${A}/agents/${id}/handoffs/${targetId}`, { method: "POST", body }),
  removeHandoff: (id: string, targetId: string) => api<AgentOut>(`${A}/agents/${id}/handoffs/${targetId}`, { method: "DELETE" }),
};

export const commandsApi = {
  list: () => api<CommandOut[]>("/agents/commands"),
};
