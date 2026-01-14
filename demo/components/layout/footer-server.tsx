import { getGithubPreview } from "@/lib/link-previews";
import { Footer } from "./footer";

export async function FooterServer() {
  let githubPreview = null;

  try {
    githubPreview = await getGithubPreview();
  } catch {
    // Fallback to no preview if fetch fails
  }

  return <Footer githubPreview={githubPreview} />;
}
