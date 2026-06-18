import type { ReactNode } from "react";
import { FooterServer } from "@/components/layout/footer-server";
import { SiteNavServer } from "@/components/layout/site-nav-server";

interface MainLayoutProps {
  children: ReactNode;
  /** Additional wrapper around children */
  contentWrapper?: "default" | "spaced";
}

/**
 * Shared main layout with navigation and footer.
 * Used by both home and demos route groups.
 */
export function MainLayout({
  children,
  contentWrapper = "default",
}: MainLayoutProps) {
  return (
    // suppressHydrationWarning: when an onboarding modal opens, Radix sets
    // aria-hidden on this background wrapper (a third-party DOM mutation React
    // doesn't track). Harmless and correct for a11y; this silences the warning.
    <div className="flex min-h-screen flex-col" suppressHydrationWarning>
      <SiteNavServer />
      <main className="mx-auto w-full max-w-6xl flex-1 px-6 pt-8 pb-24 sm:px-8">
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
