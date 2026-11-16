import { cache } from "react";
import { createClient } from "@/lib/supabase/server";
import { isEmailConfirmed } from "@/lib/api-access";
import { trialEnabled } from "@/lib/trial";
import type { User } from "@supabase/supabase-js";

export interface AccessStatus {
  user: User | null;
  isUnlocked: boolean;
  /**
   * Pending approval with a confirmed e-mail address: may run demos on the daily
   * trial allowance (lib/trial.ts).
   */
  isTrial: boolean;
  /** The per-user grant that runs the first Solution Wizard in the browser (`wizard_access`). */
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
    isTrial:
      data?.status === "pending" && isEmailConfirmed(user) && trialEnabled(),
    wizardAccess: data?.wizard_access === true,
    bypassAuth: false,
  };
});

/**
 * Whether the visitor can open /solution-wizard. The page offers both wizards
 * and is open to everyone, so this is always true. Running the first wizard in
 * the browser is another matter: that needs `wizardAccess` above, checked on
 * its API in proxy.ts.
 */
export async function getWizardAccess(): Promise<boolean> {
  return true;
}
