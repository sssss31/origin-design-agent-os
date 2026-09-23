import { api } from "@/lib/api/client";
import type { CurlPreview, CustomIntegrationOut, IntegrationTestOut, IntegrationsOverview } from "@/types/integrations";

const A = "/admin/integrations";

export interface IntegrationInput {
  name: string;
  description?: string;
  method: string;
  endpoint: string;
  headers_template: Record<string, string>;
  query_template?: Record<string, string>;
  body_template?: string | null;
  content_type?: string;
  timeout_seconds?: number;
  secrets?: { name: string; value: string; location?: string }[];
  create_tool?: boolean;
}

export const integrationsApi = {
  overview: () => api<IntegrationsOverview>(`${A}/overview`),
  list: () => api<CustomIntegrationOut[]>(A),
  get: (id: string) => api<CustomIntegrationOut>(`${A}/${id}`),
  create: (body: IntegrationInput) => api<CustomIntegrationOut>(A, { method: "POST", body }),
  update: (id: string, body: Partial<IntegrationInput> & { status?: "active" | "disabled" }) => api<CustomIntegrationOut>(`${A}/${id}`, { method: "PATCH", body }),
  remove: (id: string) => api<void>(`${A}/${id}`, { method: "DELETE" }),
  parseCurl: (curl: string) => api<CurlPreview>(`${A}/parse-curl`, { method: "POST", body: { curl } }),
  importCurl: (body: { curl: string; name: string; description?: string; create_tool?: boolean }) => api<CustomIntegrationOut>(`${A}/import-curl`, { method: "POST", body }),
  setSecret: (id: string, body: { name: string; value: string; location?: string }) => api<CustomIntegrationOut>(`${A}/${id}/secrets`, { method: "POST", body }),
  deleteSecret: (id: string, name: string) => api<CustomIntegrationOut>(`${A}/${id}/secrets/${name}`, { method: "DELETE" }),
  test: (id: string, variables: Record<string, string>) => api<IntegrationTestOut>(`${A}/${id}/test`, { method: "POST", body: { variables } }),
};
