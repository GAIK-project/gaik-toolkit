"use client";

import { createContext, useContext, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { pageUsesModelSettings } from "@/lib/model-settings";
import { useModelSettings } from "@/lib/model-settings-store";

interface RunAccess {
  loggedIn: boolean;
  /** Approved, or pending on the daily trial allowance. */
  canRun: boolean;
}

// Without a provider (state unknown) nothing is blocked: the proxy still refuses
// and the page shows its reason.
const RunAccessContext = createContext<RunAccess | null>(null);

export function RunAccessProvider({
  value,
  children,
}: {
  value: RunAccess;
  children: ReactNode;
}) {
  return (
    <RunAccessContext.Provider value={value}>
      {children}
    </RunAccessContext.Provider>
  );
}

/**
 * Whether this visitor can run the demo now, and if not, why. Runs need an
 * approved account or the trial allowance; on a demo that takes the user's own
 * model key, a saved key is enough (lib/api-access.ts).
 */
export function useRunAccess(): {
  blocked: boolean;
  loggedIn: boolean;
} {
  const access = useContext(RunAccessContext);
  const settings = useModelSettings();
  const pathname = usePathname();
  if (!access || access.canRun) return { blocked: false, loggedIn: true };
  const ownKey = !!settings && pageUsesModelSettings(pathname);
  return { blocked: !ownKey, loggedIn: access.loggedIn };
}

/**
 * Stands in for a demo's run button when the visitor cannot run it: a disabled
 * button that says why, with the way forward next to it.
 */
export function RunBlockedButton({
  size = "lg",
}: {
  size?: "default" | "sm" | "lg";
}) {
  const { loggedIn } = useRunAccess();
  return (
    <span className="flex flex-wrap items-center gap-3">
      <Button size={size} disabled>
        <Lock className="size-4" aria-hidden />
        {loggedIn ? "Waiting for approval" : "Sign in to run"}
      </Button>
      {!loggedIn && (
        <Link
          href="/sign-in"
          className="text-primary text-sm font-medium hover:underline"
        >
          Sign in
        </Link>
      )}
    </span>
  );
}
