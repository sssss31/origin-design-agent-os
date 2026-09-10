import { api } from "@/lib/api/client";
import type {
  ProjectOut,
  ProjectRuleOut,
  WorkspaceCreate,
  WorkspaceMemberOut,
  WorkspaceOut,
} from "@/types/api";

/** Fired on `window` whenever the set of workspaces changes so the sidebar can refetch. */
export const WORKSPACES_CHANGED = "origin:workspaces-changed";

function notifyWorkspacesChanged<T>(value: T): T {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(WORKSPACES_CHANGED));
  return value;
}

export const workspacesApi = {
  list: () => api<WorkspaceOut[]>("/workspaces"),
  create: (body: WorkspaceCreate) =>
    api<WorkspaceOut>("/workspaces", { method: "POST", body }).then(notifyWorkspacesChanged),
  get: (id: string) => api<WorkspaceOut>(`/workspaces/${id}`),
  update: (id: string, body: Partial<Pick<WorkspaceOut, "name" | "description" | "rules_text" | "status">>) =>
    api<WorkspaceOut>(`/workspaces/${id}`, { method: "PATCH", body }).then(notifyWorkspacesChanged),
  members: (id: string) => api<WorkspaceMemberOut[]>(`/workspaces/${id}/members`),
  addMember: (id: string, email: string, role: string) =>
    api<WorkspaceMemberOut>(`/workspaces/${id}/members`, { method: "POST", body: { email, role } }),
  projects: (id: string) => api<ProjectOut[]>(`/workspaces/${id}/projects`),
  createProject: (id: string, body: { name: string; description?: string }) =>
    api<ProjectOut>(`/workspaces/${id}/projects`, { method: "POST", body }),
};

export const projectsApi = {
  get: (id: string) => api<ProjectOut>(`/projects/${id}`),
  update: (id: string, body: Partial<Pick<ProjectOut, "name" | "description" | "summary_text" | "status">>) =>
    api<ProjectOut>(`/projects/${id}`, { method: "PATCH", body }),
  rules: (id: string) => api<ProjectRuleOut[]>(`/projects/${id}/rules`),
  createRule: (id: string, body: { name: string; rule_text: string; priority?: number }) =>
    api<ProjectRuleOut>(`/projects/${id}/rules`, { method: "POST", body }),
  updateRule: (id: string, ruleId: string, body: Partial<Pick<ProjectRuleOut, "name" | "rule_text" | "priority" | "is_active">>) =>
    api<ProjectRuleOut>(`/projects/${id}/rules/${ruleId}`, { method: "PATCH", body }),
};
