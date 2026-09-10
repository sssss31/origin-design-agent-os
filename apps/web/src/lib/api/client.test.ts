import { describe, expect, it } from "vitest";
import { ApiError, parseErrorBody } from "@/lib/api/client";

describe("parseErrorBody", () => {
  it("maps the API error envelope", () => {
    const err = parseErrorBody(404, { error: { code: "workspace_not_found", message: "Workspace not found", request_id: "r1" } });
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(404);
    expect(err.code).toBe("workspace_not_found");
    expect(err.requestId).toBe("r1");
  });

  it("falls back for non-envelope bodies", () => {
    const err = parseErrorBody(502, "<html>bad gateway</html>");
    expect(err.code).toBe("http_error");
    expect(err.message).toContain("502");
  });
});
