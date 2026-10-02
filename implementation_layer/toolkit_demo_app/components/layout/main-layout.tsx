import type { ReactNode } from "react";
import { FooterServer } from "@/components/layout/footer-server";
import { SiteNavServer } from "@/components/layout/site-nav-server";
import { AccessNotice, ModelSettingsNotice } from "@/components/model-settings";
import { getUserAccessStatus } from "@/lib/queries/access";

interface MainLayoutProps {
  children: ReactNode;
  /** Additional wrapper around children */
  contentWrapper?: "default" | "spaced";
  /** Demo pages explain how to run when the visitor is not signed in or approved. */
  accessNotice?: boolean;
}

/**
 * Shared main layout with navigation and footer.
 * Used by both home and demos route groups.
 */
export async function MainLayout({
  children,
  contentWrapper = "default",
  accessNotice = false,
}: MainLayoutProps) {
  let access = null;
  if (accessNotice) {
    try {
      access = await getUserAccessStatus();
    } catch {
      // Without a known state, show no notice rather than a wrong one.
    }
  }
  return (
    // suppressHydrationWarning: when an onboarding modal opens, Radix sets
    // aria-hidden on this background wrapper (a third-party DOM mutation React
    // doesn't track). Harmless and correct for a11y; this silences the warning.
    <div className="flex min-h-screen flex-col" suppressHydrationWarning>
      <SiteNavServer />
      <main className="mx-auto w-full max-w-6xl flex-1 px-6 pt-8 pb-24 sm:px-8">
        {access && (
          <AccessNotice loggedIn={!!access.user} unlocked={access.isUnlocked} />
        )}
        <ModelSettingsNotice />
        {contentWrapper === "spaced" ? (
          <div className="space-y-6">{children}</div>
        ) : (
          children
        )}
      </main>
      <FooterServer />
    </div>
  );
}
