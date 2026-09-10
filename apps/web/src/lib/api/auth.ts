import { api } from "@/lib/api/client";
import { tokenStore } from "@/lib/token-store";
import type { MeResponse, TokenResponse } from "@/types/api";

export async function login(email: string, password: string): Promise<TokenResponse> {
  const pair = await api<TokenResponse>("/auth/login", { method: "POST", body: { email, password }, auth: false });
  tokenStore.set(pair.access_token, pair.refresh_token);
  return pair;
}

export async function logout(): Promise<void> {
  const refresh = tokenStore.getRefreshToken();
  try {
    if (refresh) await api<void>("/auth/logout", { method: "POST", body: { refresh_token: refresh }, retryOn401: false });
  } finally {
    tokenStore.clear();
  }
}

export function fetchMe(): Promise<MeResponse> {
  return api<MeResponse>("/me");
}
