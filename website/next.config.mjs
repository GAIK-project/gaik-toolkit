import { createMDX } from "fumadocs-mdx/next";

const withMDX = createMDX();

const isGitHubPages = !process.env.LOCAL_PREVIEW;

/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  output: "export",
  basePath: isGitHubPages ? "/gaik-toolkit" : "",
  assetPrefix: isGitHubPages ? "/gaik-toolkit/" : "",
  images: { unoptimized: true },
  trailingSlash: true,
};

export default withMDX(config);
