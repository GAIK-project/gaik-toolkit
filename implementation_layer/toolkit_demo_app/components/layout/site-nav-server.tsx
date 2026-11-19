import { type Account, accountOf } from "@/lib/account";
import { getUserAccessStatus, getWizardAccess } from "@/lib/queries/access";
import { getTrialLimits } from "@/lib/trial";
import { headers } from "next/headers";
import { SiteNav } from "./site-nav";

export async function SiteNavServer() {
  // Get pathname from proxy header for SSR active state
  const headersList = await headers();
  const pathname = headersList.get("x-current-path") || "/";

  // The /solution-wizard page is a notice open to everyone (getWizardAccess),
  // so the nav shows it as a link rather than a locked "Beta" tile.
  let isLoggedIn = false;
  let account: Account | null = null;
  try {
    // BYPASS_AUTH (local development) runs everything without an account.
    const access = await getUserAccessStatus();
    isLoggedIn = !!access.user || access.bypassAuth;
    account = accountOf(access, getTrialLimits().runsPerDay);
  } catch {
    // ignore auth errors
  }
  const hasWizardAccess = await getWizardAccess();

  return (
    <SiteNav
      pathname={pathname}
      isLoggedIn={isLoggedIn}
      account={account}
      hasWizardAccess={hasWizardAccess}
    />
  );
}
