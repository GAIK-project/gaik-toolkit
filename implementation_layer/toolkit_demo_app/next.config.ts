import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  compress: false, // Required for SSE streaming - prevents gzip buffering
  reactCompiler: true,
  output: "standalone",
  images: {
    unoptimized: true,
  },
  serverExternalPackages: ["shiki"],
  async rewrites() {
    return [
      {
        source: "/a/static/:path*",
        destination: "https://eu-assets.i.posthog.com/static/:path*",
      },
      {
        source: "/a/:path*",
        destination: "https://eu.i.posthog.com/:path*",
      },
    ];
  },
};

export default nextConfig;
