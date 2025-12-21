import { createMDX } from "fumadocs-mdx/next";

const withMDX = createMDX();

/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  output: "export",
  basePath: "/gaik-toolkit",
  assetPrefix: "/gaik-toolkit/",
  images: { unoptimized: true },
  trailingSlash: true,
};

export default withMDX(config);
