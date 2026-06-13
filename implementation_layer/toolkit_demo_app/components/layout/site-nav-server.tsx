import { getGithubPreviewSafe } from "@/lib/link-previews";
import { createClient } from "@/lib/supabase/server";
import { cookies, headers } from "next/headers";
import { SiteNav } from "./site-nav";

export async function SiteNavServer() {
  const githubPreview = await getGithubPreviewSafe();

  // Get pathname from proxy header for SSR active state
  const headersList = await headers();
  const pathname = headersList.get("x-current-path") || "/";

  // Beta gate: the Solution Wizard unlocks once a visitor supplies the ?key=
  // secret (which sets the httpOnly `wizard_access` cookie). Mirror the proxy's
  // check here so the nav shows a real link to beta users and a locked "Beta"
  // item to everyone else. Default-deny when no secret is configured.
  const cookieStore = await cookies();
  const wizardSecret = process.env.WIZARD_ACCESS_SECRET;
  const hasWizardAccess =
    !!wizardSecret &&
    cookieStore.get("wizard_access")?.value === wizardSecret;

  let isLoggedIn = false;
  try {
    const supabase = await createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();
    isLoggedIn = !!user;
  } catch {
    // ignore auth errors
  }

  return (
    <SiteNav
      pathname={pathname}
      githubPreview={githubPreview}
      isLoggedIn={isLoggedIn}
    />
  );
}
