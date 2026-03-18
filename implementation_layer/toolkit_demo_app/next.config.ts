import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // SSE Streaming Fix for OpenShift/Rahti:
  // Next.js enables gzip compression by default in production, which buffers
  // entire SSE responses before sending. This breaks real-time progress updates
  // (e.g., "AI is working..." instead of step-by-step progress).
  // Setting compress: false allows chunked transfer encoding to work properly.
  // See: https://medium.com/@oyetoketoby80/fixing-slow-sse-server-sent-events-streaming-in-next-js-and-vercel-99f42fbdb996
  // compress: false,
  allowedDevOrigins: ["*.local", "10.*"],
  reactCompiler: true,
  output: "standalone",
  images: {
    unoptimized: true,
  },
  serverExternalPackages: ["shiki"],
  experimental: {
    proxyClientMaxBodySize: "50mb",
  },
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
