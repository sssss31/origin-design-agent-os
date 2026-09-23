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
  name: string;
  slug: string;
  method: string;
  endpoint: string;
  status: "active" | "disabled";
  headers_template: Record<string, string>;
  body_template: string | null;
  content_type: string;
  timeout_seconds: number;
  secrets: { name: string; fingerprint: string; rotated_at: string | null }[];
  variables: string[];
  tool_id: string | null;
  tool_slug: string | null;
  used_by: string[];
  health_status: "unknown" | "ok" | "error";
  health_message: string | null;
  last_tested_at: string | null;
  avg_latency_ms: number | null;
  request_count: number;
  created_at: string;
  updated_at: string;
}

export interface IntegrationsOverview {
  provider_types: ProviderTypeInfo[];
  providers: ProviderCard[];
  custom: CustomIntegrationOut[];
}
