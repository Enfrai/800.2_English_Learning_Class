// Configure Next.js for the containerized frontend.
// Author: Shuohui Liu
// Date: 19 Oct 2026

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  experimental: { globalNotFound: true },
};

export default nextConfig;
