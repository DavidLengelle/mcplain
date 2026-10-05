import type { NextConfig } from "next";

import { apiBaseUrl } from "./src/lib/api-url";

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

export default nextConfig;
