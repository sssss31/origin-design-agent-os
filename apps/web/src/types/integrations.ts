import type { ProviderOut } from "@/types/admin";

export interface ProviderCard {
  provider: ProviderOut;
  used_by: string[];
  requests_month: number;
  tokens_month: number;
  avg_latency_ms: number | null;
  estimated_cost_month_usd: number | null;
}

export interface ProviderTypeInfo {
  type: string;
  display_name: string;
  supported_models: { model: string; display_name: string; capabilities: Record<string, unknown> }[];
}

export interface CustomIntegrationOut {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  description: string;
  method: string;
  endpoint: string;
  status: "active" | "disabled";
  headers_template: Record<string, string>;
  query_template: Record<string, string>;
  body_template: string | null;
  content_type: string;
  timeout_seconds: number;
  max_response_bytes: number;
  auth_summary: string;
  secrets: { name: string; fingerprint: string; key_preview: string | null; location: string; rotated_at: string | null; created_at: string }[];
  variables: string[];
  missing_secrets: string[];
  tool_id: string | null;
  tool_slug: string | null;
  used_by: string[];
  health_status: "unknown" | "ok" | "error";
  health_message: string | null;
  last_tested_at: string | null;
  avg_latency_ms: number | null;
  request_count: number;
  error_count: number;
  created_at: string;
  updated_at: string;
}

export interface CurlPreview {
  method: string;
  url: string;
  headers: Record<string, string>;
  query: Record<string, string>;
  body: string | null;
  content_type: string;
  body_kind: string;
  secrets: { name: string; location: string; hint: string; preview: string }[];
  variables: string[];
  warnings: string[];
  summary: Record<string, string>;
}

export interface IntegrationTestOut {
  ok: boolean;
  request: { method?: string; url?: string; query?: Record<string, string>; headers?: Record<string, string>; body?: string | null; error?: string };
  status: number | null;
  latency_ms: number;
  response_size_bytes: number | null;
  content_type: string | null;
  response_preview: unknown;
  file: string | null;
  error_code: string | null;
  error_message: string | null;
  tested_at: string;
}

export interface IntegrationsOverview {
  provider_types: ProviderTypeInfo[];
  providers: ProviderCard[];
  custom: CustomIntegrationOut[];
}
