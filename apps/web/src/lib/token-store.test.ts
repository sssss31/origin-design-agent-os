import { describe, expect, it } from "vitest";
import { tokenStore } from "@/lib/token-store";

describe("tokenStore (no window)", () => {
  it("keeps the access token in memory only and survives missing storage", () => {
    tokenStore.set("access", "refresh");
    expect(tokenStore.getAccessToken()).toBe("access");
    expect(tokenStore.getRefreshToken()).toBeNull(); // no localStorage in node
    tokenStore.clear();
    expect(tokenStore.getAccessToken()).toBeNull();
  });
});
