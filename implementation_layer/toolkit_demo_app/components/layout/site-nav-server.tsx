import { getGithubPreviewSafe } from "@/lib/link-previews";
import { getUserAccessStatus, getWizardAccess } from "@/lib/queries/access";
import { headers } from "next/headers";
import { SiteNav } from "./site-nav";

export async function SiteNavServer() {
  const githubPreview = await getGithubPreviewSafe();

  // Get pathname from proxy header for SSR active state
  const headersList = await headers();
  const pathname = headersList.get("x-current-path") || "/";

  // Solution Wizard nav state mirrors the proxy gate so the nav shows a real
  // link to people who can actually open it and a locked "Beta" tile to
  // everyone else. Unlocked for either:
  //   - the team `?key=` cookie holders (httpOnly `wizard_access` cookie), or
  //   - a registered user granted the per-user `wizard_access` flag.
  // Default-deny otherwise.
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
