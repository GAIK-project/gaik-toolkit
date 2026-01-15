import { getGithubPreviewSafe } from "@/lib/link-previews";
import { Footer } from "./footer";

export async function FooterServer() {
  const githubPreview = await getGithubPreviewSafe();
  return <Footer githubPreview={githubPreview} />;
}
