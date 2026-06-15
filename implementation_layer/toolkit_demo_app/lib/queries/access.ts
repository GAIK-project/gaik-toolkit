import { cache } from "react";
import { createClient } from "@/lib/supabase/server";
import type { User } from "@supabase/supabase-js";

export interface AccessStatus {
  user: User | null;
  isUnlocked: boolean;
  /** Per-user Solution Wizard beta access (the `wizard_access` flag). */
  wizardAccess: boolean;
  bypassAuth: boolean;
}

export const getUserAccessStatus = cache(async (): Promise<AccessStatus> => {
  const bypassAuth = process.env.BYPASS_AUTH === "true";

  if (bypassAuth) {
    return { user: null, isUnlocked: true, wizardAccess: true, bypassAuth: true };
  }

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return {
      user: null,
      isUnlocked: false,
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
    wizardAccess: data?.wizard_access === true,
    bypassAuth: false,
  };
});
