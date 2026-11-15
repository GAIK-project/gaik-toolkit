import { cache } from "react";
import { createClient } from "@/lib/supabase/server";
import { trialEnabled } from "@/lib/trial";
import type { User } from "@supabase/supabase-js";

export interface AccessStatus {
  user: User | null;
  isUnlocked: boolean;
  /** Pending approval, but may run demos on the daily trial allowance (lib/trial.ts). */
  isTrial: boolean;
  /** Per-user Solution Wizard beta access (the `wizard_access` flag). */
  wizardAccess: boolean;
  bypassAuth: boolean;
}

export const getUserAccessStatus = cache(async (): Promise<AccessStatus> => {
  const bypassAuth = process.env.BYPASS_AUTH === "true";

  if (bypassAuth) {
    return {
      user: null,
      isUnlocked: true,
      isTrial: false,
      wizardAccess: true,
      bypassAuth: true,
    };
  }

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return {
      user: null,
      isUnlocked: false,
      isTrial: false,
      wizardAccess: false,
      bypassAuth: false,
    };
  }

  const { data } = await supabase
    .from("access_requests")
    .select("status, wizard_access")
    .eq("user_id", user.id)
    .single();

  return {
    user,
    isUnlocked: data?.status === "approved",
    isTrial: data?.status === "pending" && trialEnabled(),
    wizardAccess: data?.wizard_access === true,
    bypassAuth: false,
  };
});

/**
 * Whether the visitor can open /solution-wizard. The page is now a notice that
 * links to Wizard V2 and proxy.ts lets everyone through, so this is always true;
 * the nav and the home page entries keep their access branches until the
 * wizard_access grant is removed.
 */
export async function getWizardAccess(): Promise<boolean> {
  return true;
}
