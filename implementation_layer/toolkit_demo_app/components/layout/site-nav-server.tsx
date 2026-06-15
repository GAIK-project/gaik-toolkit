import { getGithubPreviewSafe } from "@/lib/link-previews";
import { getUserAccessStatus } from "@/lib/queries/access";
import { cookies, headers } from "next/headers";
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
  const cookieStore = await cookies();
  const wizardSecret = process.env.WIZARD_ACCESS_SECRET;
  const teamCookie =
    !!wizardSecret && cookieStore.get("wizard_access")?.value === wizardSecret;

  let isLoggedIn = false;
  let dbWizardAccess = false;
  try {
    const access = await getUserAccessStatus();
    isLoggedIn = !!access.user;
    dbWizardAccess = access.wizardAccess;
  } catch {
    // ignore auth errors
  }

  const hasWizardAccess = teamCookie || dbWizardAccess;

  return (
    <SiteNav
      pathname={pathname}
      githubPreview={githubPreview}
      isLoggedIn={isLoggedIn}
      hasWizardAccess={hasWizardAccess}
    />
  );
}
