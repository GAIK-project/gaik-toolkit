"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { cookies, headers } from "next/headers";
import { createClient } from "@/lib/supabase/server";
import { DEV_COOKIE, validateDevCredentials } from "@/lib/auth";
import { devAuthActive, hasWizardAccess } from "@/lib/supabase-auth";
import { audit } from "@/lib/audit";
import { DEV_SESSION_MAX_AGE_S, signDevSession, verifyDevSession } from "@/lib/dev-session";
import { getIncomingTraceId } from "@/lib/request-context";
import { accountKey, addressKey, clientAddress, devLoginCounter } from "@/lib/login-throttle";
import {
  ACCESS_TOKEN_HEADER,
  proxyAuthEnabled,
  proxySignOutUrl,
  verifyAccessToken,
} from "@/lib/proxy-auth";

/** X-Forwarded-For of the sign-in request, or null outside a request scope. */
async function forwardedFor(): Promise<string | null> {
  try {
    return (await headers()).get("x-forwarded-for");
  } catch {
    return null;
  }
}

async function devSignIn(formData: FormData) {
  const email = formData.get("email") as string;
  const password = formData.get("password") as string;
  const traceId = await getIncomingTraceId();

  // Repeated failures from one account or one client address are refused for
  // a while (lib/login-throttle), with the same message as a wrong password,
  // before the password is even compared: a refused attempt says nothing about
  // the account or the password. Only failures count.
  const counter = devLoginCounter();
  const address = clientAddress(await forwardedFor());
  const keys = [accountKey(email ?? ""), ...(address ? [addressKey(address)] : [])];
  if (keys.some((key) => counter.isBlocked(key))) {
    audit("auth.login", {
      actor: email,
      outcome: "denied",
      reason: "throttled",
      traceId,
      mode: "dev",
    });
    redirect("/login?error=credentials");
  }

  if (validateDevCredentials(email, password)) {
    const cookieStore = await cookies();
    // Signed and expiring (lib/dev-session): a cookie nobody can write by hand.
    // `secure` follows the environment: the Rahti route terminates TLS, a local
    // `next dev` on http would otherwise never receive the cookie back.
    let cookie: string;
    try {
      cookie = await signDevSession(email);
    } catch {
      // No signing key on this build (lib/dev-session): nobody can sign in.
      redirect("/login?error=unavailable");
    }
    cookieStore.set(DEV_COOKIE, cookie, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      maxAge: DEV_SESSION_MAX_AGE_S,
      path: "/",
    });
    counter.reset(accountKey(email));
    audit("auth.login", { actor: email, outcome: "success", traceId, mode: "dev" });
    revalidatePath("/", "layout");
    redirect("/");
  }

  for (const key of keys) counter.recordFailure(key);
  // Never log the attempted password — only the email that was tried.
  audit("auth.login", { actor: email, outcome: "denied", traceId, mode: "dev" });
  // The message names no account and no password: it used to list every dev
  // account with its password, on instances anyone can reach.
  redirect("/login?error=credentials");
}

export async function login(formData: FormData) {
  // Behind the sign-in proxy there is no password form: the proxy signed the
  // user in before this page was reached.
  if (proxyAuthEnabled()) redirect("/");
  if (devAuthActive()) return devSignIn(formData);

  const email = formData.get("email") as string;
  const traceId = await getIncomingTraceId();
  const supabase = await createClient();
  const { data, error } = await supabase.auth.signInWithPassword({
    email,
    password: formData.get("password") as string,
  });

  if (error) {
    audit("auth.login", { actor: email, outcome: "denied", traceId, mode: "supabase" });
    redirect("/login?error=credentials");
  }

  // A valid Supabase password is not enough: anyone can create an account in
  // the project with its public key. Only confirmed accounts with access to the
  // wizard (lib/supabase-auth) stay signed in; the others are told the account
  // is waiting, which says no more than the demo's own pages do.
  if (!(await hasWizardAccess(supabase, data.user))) {
    await supabase.auth.signOut();
    audit("auth.login", {
      actor: email,
      outcome: "denied",
      reason: "no_access",
      traceId,
      mode: "supabase",
    });
    redirect("/login?error=pending");
  }

  audit("auth.login", { actor: email, outcome: "success", traceId, mode: "supabase" });
  revalidatePath("/", "layout");
  redirect("/");
}

export async function signOut() {
  const traceId = await getIncomingTraceId();
  if (proxyAuthEnabled()) {
    const user = await verifyAccessToken((await headers()).get(ACCESS_TOKEN_HEADER));
    if (user) audit("auth.logout", { actor: user.email, outcome: "success", traceId, mode: "proxy" });
    // The proxy clears its own cookie and then ends the Keycloak session.
    redirect(proxySignOutUrl());
  }
  if (devAuthActive()) {
    const cookieStore = await cookies();
    const email = await verifyDevSession(cookieStore.get(DEV_COOKIE)?.value);
    cookieStore.delete(DEV_COOKIE);
    if (email) audit("auth.logout", { actor: email, outcome: "success", traceId, mode: "dev" });
    revalidatePath("/", "layout");
    redirect("/login");
  }

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  await supabase.auth.signOut();
  if (user?.email) {
    audit("auth.logout", { actor: user.email, outcome: "success", traceId, mode: "supabase" });
  }
  revalidatePath("/", "layout");
  redirect("/login");
}
