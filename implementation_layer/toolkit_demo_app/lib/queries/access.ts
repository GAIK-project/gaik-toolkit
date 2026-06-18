import { cookies } from "next/headers";
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

/**
 * Whether the current request can actually open the Solution Wizard — the
 * per-user `wizard_access` grant (or BYPASS_AUTH) OR the team `?key=` cookie.
 * Mirrors the gate in proxy.ts so the UI matches who can really get in.
 */
export async function getWizardAccess(): Promise<boolean> {
  if ((await getUserAccessStatus()).wizardAccess) return true;
  const secret = process.env.WIZARD_ACCESS_SECRET;
  if (!secret) return false;
  const cookieStore = await cookies();
  return cookieStore.get("wizard_access")?.value === secret;
}
