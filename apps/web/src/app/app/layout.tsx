"use client";

import { useEffect } from "react";
import { AppShell } from "@/components/shell/AppShell";
import { applyTheme, readTheme } from "@/lib/theme";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    applyTheme(readTheme());
  }, []);
  return <AppShell>{children}</AppShell>;
}
