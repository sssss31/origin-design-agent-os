"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { fetchMe, login as apiLogin, logout as apiLogout } from "@/lib/api/auth";
import { tokenStore } from "@/lib/token-store";
import type { MeResponse } from "@/types/api";

interface SessionState {
  status: "loading" | "anonymous" | "authenticated";
  me: MeResponse | null;
  organizationId: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  setOrganization: (id: string) => void;
  refresh: () => Promise<void>;
}

const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<SessionState["status"]>("loading");
  const [me, setMe] = useState<MeResponse | null>(null);
  const [organizationId, setOrganizationId] = useState<string | null>(null);

  // Promise-chain style on purpose: React's `set-state-in-effect` rule only allows setState
  // inside callbacks, never synchronously in the effect body.
  const load = useCallback(() => {
    const hasSession = Boolean(tokenStore.getRefreshToken() || tokenStore.getAccessToken());
    const request = hasSession ? fetchMe() : Promise.reject(new Error("anonymous"));
    return request
      .then((data) => {
        setMe(data);
        const stored = tokenStore.getOrganizationId();
        const valid = data.memberships.find((m) => m.organization_id === stored)?.organization_id;
        const chosen = valid ?? data.active_organization_id ?? data.memberships[0]?.organization_id ?? null;
        tokenStore.setOrganizationId(chosen);
        setOrganizationId(chosen);
        setStatus("authenticated");
      })
      .catch(() => {
        tokenStore.clear();
        setMe(null);
        setStatus("anonymous");
      });
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const value = useMemo<SessionState>(
    () => ({
      status,
      me,
      organizationId,
      login: async (email, password) => {
        await apiLogin(email, password);
        await load();
      },
      logout: async () => {
        await apiLogout();
        setMe(null);
        setOrganizationId(null);
        setStatus("anonymous");
      },
      setOrganization: (id) => {
        tokenStore.setOrganizationId(id);
        setOrganizationId(id);
      },
      refresh: load,
    }),
    [status, me, organizationId, load],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside SessionProvider");
  return ctx;
}
