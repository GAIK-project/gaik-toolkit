"use client";

import { useOnboarding } from "@/components/onboarding/onboarding-provider";
import Link from "next/link";
import type { ReactNode } from "react";

export interface WizardAccess {
  hasWizardAccess: boolean;
  isAuthenticated: boolean;
}

/**
 * The way into the Solution Configuration Wizard (beta). Access holders go straight
 * in; anonymous visitors follow the same sign-in path as the other demos; signed-in
 * users without the grant get the beta access dialog.
 */
export function WizardEntry({
  hasWizardAccess,
  isAuthenticated,
  className,
  tour,
  children,
}: WizardAccess & { className?: string; tour?: string; children: ReactNode }) {
  const { openWizardAccess } = useOnboarding();

  if (hasWizardAccess)
    return (
      <Link href="/solution-wizard" data-tour={tour} className={className}>
        {children}
      </Link>
    );
  if (!isAuthenticated)
    return (
      <Link href="/sign-in" data-tour={tour} className={className}>
        {children}
      </Link>
    );
  return (
    <button
      type="button"
      data-tour={tour}
      onClick={openWizardAccess}
      className={className}
    >
      {children}
    </button>
  );
}
