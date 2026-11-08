import { glimpse } from "@/components/kibo-ui/glimpse/server";

export const GITHUB_REPO_URL = "https://github.com/GAIK-project/gaik-toolkit";

export type LinkPreview = {
  title: string | null;
  description: string | null;
  image: string | null;
};

// Every page renders the preview, so a slow github.com must not hold up a
// page or the image build (prerendering gives up on a page after 60 s).
export const PREVIEW_TIMEOUT_MS = 5000;

export async function getGithubPreview(): Promise<LinkPreview> {
  return glimpse(GITHUB_REPO_URL, {
    signal: AbortSignal.timeout(PREVIEW_TIMEOUT_MS),
  });
}

export async function getGithubPreviewSafe(): Promise<LinkPreview | null> {
  try {
    return await getGithubPreview();
  } catch {
    return null;
  }
}
