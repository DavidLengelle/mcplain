import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

import { apiBaseUrl } from "./src/lib/api-url";
import { SECURITY_HEADERS } from "./src/lib/security-headers";

const withNextIntl = createNextIntlPlugin();

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  agentRules: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: Object.entries(SECURITY_HEADERS).map(([key, value]) => ({ key, value })),
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiBaseUrl()}/api/:path*`,
      },
    ];
  },
};

export default withNextIntl(nextConfig);
