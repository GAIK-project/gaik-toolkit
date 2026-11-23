// Shared helper to get the signed-in user.
// Works in both dev mode (cookie) and Supabase mode, with the same logic
// as the proxy (proxy.ts) and login action. Use this in server components; do not
// repeat the DEV_AUTH branching on every page.

import { cache } from "react";
import { cookies, headers } from "next/headers";
import { createClient } from "@/lib/supabase/server";
import { DEV_COOKIE } from "@/lib/auth";
import { devAuthActive, hasWizardAccess } from "@/lib/supabase-auth";
import { verifyDevSession } from "@/lib/dev-session";
import { ACCESS_TOKEN_HEADER, proxyAuthEnabled, verifyAccessToken } from "@/lib/proxy-auth";

export type CurrentUser = { email: string };

// One lookup per request: the shell's layout and the page under it both ask.
export const getCurrentUser = cache(async (): Promise<CurrentUser | null> => {
  // Proxy sign-in (lib/proxy-auth) comes first: an image built with the dev
  // login on runs with it off when WIZARD_AUTH_MODE=proxy, and a dev cookie
  // then signs nobody in.
  if (proxyAuthEnabled()) {
    const user = await verifyAccessToken((await headers()).get(ACCESS_TOKEN_HEADER));
    return user ? { email: user.email } : null;
  }

  if (devAuthActive()) {
    const cookieStore = await cookies();
    const email = await verifyDevSession(cookieStore.get(DEV_COOKIE)?.value);
    return email ? { email } : null;
  }

  const supabase = await createClient();
  const { data } = await supabase.auth.getUser();
  // A Supabase account alone is not enough: only confirmed accounts with access
  // to the wizard (lib/supabase-auth).
  const user = data.user;
  return user?.email && (await hasWizardAccess(supabase, user)) ? { email: user.email } : null;
});
