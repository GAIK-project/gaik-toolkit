import { getGithubPreviewSafe } from "@/lib/link-previews";
import { SiteNav } from "./site-nav";

export async function SiteNavServer() {
  const githubPreview = await getGithubPreviewSafe();
  return <SiteNav githubPreview={githubPreview} />;
}
