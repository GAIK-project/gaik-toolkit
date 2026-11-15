import { getGithubPreviewSafe } from "@/lib/link-previews";
import { getUserAccessStatus, getWizardAccess } from "@/lib/queries/access";
import { headers } from "next/headers";
import { SiteNav } from "./site-nav";

export async function SiteNavServer() {
  const githubPreview = await getGithubPreviewSafe();

  // Get pathname from proxy header for SSR active state
  const headersList = await headers();
  const pathname = headersList.get("x-current-path") || "/";

  // The /solution-wizard page is a notice open to everyone (getWizardAccess),
  // so the nav shows it as a link rather than a locked "Beta" tile.
  let isLoggedIn = false;
  try {
    isLoggedIn = !!(await getUserAccessStatus()).user;
  } catch {
    // ignore auth errors
  }
  const hasWizardAccess = await getWizardAccess();

  return (
    <SiteNav
      pathname={pathname}
      githubPreview={githubPreview}
      isLoggedIn={isLoggedIn}
      hasWizardAccess={hasWizardAccess}
    />
  );
}
