import type { NextConfig } from "next";

/**
 * The browser talks to `/api/v1/*` on the web origin; Next proxies it to the API so no CORS
 * or public API URL is needed in development. Set API_PROXY_TARGET to the API origin
 * (default http://localhost:8000). Set NEXT_PUBLIC_API_BASE_URL to call the API directly.
 */
const apiProxyTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${apiProxyTarget}/api/v1/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
