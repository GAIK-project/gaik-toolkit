import { glimpse } from "@/components/kibo-ui/glimpse/server";

export const GITHUB_REPO_URL = "https://github.com/GAIK-project/gaik-toolkit";

export type LinkPreview = {
  title: string | null;
  description: string | null;
  image: string | null;
};

export async function getGithubPreview(): Promise<LinkPreview> {
  return glimpse(GITHUB_REPO_URL);
}

export async function getGithubPreviewSafe(): Promise<LinkPreview | null> {
  try {
    return await getGithubPreview();
  } catch {
    return null;
  }
}
