import { cache } from "react";
import { getGithubPreviewSafe } from "@/lib/link-previews";
import { Footer } from "./footer";

const getCachedGithubPreview = cache(async () => {
  return getGithubPreviewSafe();
});

export async function FooterServer() {
  const githubPreview = await getCachedGithubPreview();
  return <Footer githubPreview={githubPreview} />;
}
