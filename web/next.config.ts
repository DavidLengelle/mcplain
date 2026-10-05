import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

import { apiBaseUrl } from "./src/lib/api-url";

const withNextIntl = createNextIntlPlugin();

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
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
