import { NextResponse } from "next/server";

/**
 * Reached only when next.config.ts has no API proxy (API_PROXY_TARGET unset on a hosted build).
 * The rewrite in next.config.ts takes precedence whenever the proxy is configured.
 */
function notConfigured() {
  return NextResponse.json(
    {
      error: {
        code: "api_not_configured",
        message: "The web app is not connected to an API. Set API_PROXY_TARGET to the API origin (for example https://origin-api.onrender.com) in the web deployment's environment variables and redeploy. See docs/DEPLOY.md.",
      },
    },
    { status: 503 },
  );
}

export const GET = notConfigured;
export const POST = notConfigured;
export const PUT = notConfigured;
export const PATCH = notConfigured;
export const DELETE = notConfigured;
