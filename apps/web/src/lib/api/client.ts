import type { ApiErrorBody } from "@/types/api";
import { tokenStore } from "@/lib/token-store";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
    public requestId?: string | null,
  ) {
    super(message);
  }
}

export function parseErrorBody(status: number, body: unknown): ApiError {
  const err = (body as ApiErrorBody | undefined)?.error;
  if (err && typeof err.code === "string") {
    return new ApiError(status, err.code, err.message, err.details, err.request_id);
  }
  return new ApiError(status, "http_error", `Request failed with status ${status}`);
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  auth?: boolean;
  organizationId?: string | null;
  retryOn401?: boolean;
}

let refreshInFlight: Promise<boolean> | null = null;

/** Rotate the refresh token once; concurrent callers share the same attempt. */
async function tryRefresh(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const refresh = tokenStore.getRefreshToken();
      if (!refresh) return false;
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!res.ok) {
        tokenStore.clear();
        return false;
      }
      const pair = (await res.json()) as { access_token: string; refresh_token: string };
      tokenStore.set(pair.access_token, pair.refresh_token);
      return true;
    })().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, auth = true, organizationId, retryOn401 = true } = options;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  // After a reload only the refresh token survives: obtain an access token first instead of
  // sending a request that is guaranteed to fail with 401.
  if (auth && !tokenStore.getAccessToken() && tokenStore.getRefreshToken()) await tryRefresh();
  if (auth) {
    const token = tokenStore.getAccessToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  const org = organizationId ?? tokenStore.getOrganizationId();
  if (org) headers["X-Organization-Id"] = org;

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401 && auth && retryOn401 && (await tryRefresh())) {
    return api<T>(path, { ...options, retryOn401: false });
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? (JSON.parse(text) as unknown) : undefined;
  if (!res.ok) throw parseErrorBody(res.status, data);
  return data as T;
}
