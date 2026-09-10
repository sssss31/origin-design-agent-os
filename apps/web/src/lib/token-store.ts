/**
 * Browser-side token storage.
 *
 * Access token: memory only (never persisted). Refresh token: localStorage so a reload keeps
 * the session; it is rotated on every use and the API revokes the whole family on reuse.
 * Phase 8 hardening moves the refresh token to an httpOnly cookie + CSRF token.
 */

const REFRESH_KEY = "origin.refresh_token";
const ORG_KEY = "origin.organization_id";

let accessToken: string | null = null;

function storage(): Storage | null {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null;
  }
}

export const tokenStore = {
  getAccessToken: () => accessToken,
  getRefreshToken: () => storage()?.getItem(REFRESH_KEY) ?? null,
  getOrganizationId: () => storage()?.getItem(ORG_KEY) ?? null,
  set(access: string, refresh: string) {
    accessToken = access;
    storage()?.setItem(REFRESH_KEY, refresh);
  },
  setOrganizationId(id: string | null) {
    if (id) storage()?.setItem(ORG_KEY, id);
    else storage()?.removeItem(ORG_KEY);
  },
  clear() {
    accessToken = null;
    storage()?.removeItem(REFRESH_KEY);
    storage()?.removeItem(ORG_KEY);
  },
  /** Test helper: inject an access token without touching storage. */
  _setAccessTokenForTests(token: string | null) {
    accessToken = token;
  },
};
