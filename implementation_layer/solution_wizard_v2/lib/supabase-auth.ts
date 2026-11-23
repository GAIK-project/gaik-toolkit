// Sign-in through the GAIK demo's Supabase project (WIZARD_AUTH_MODE=supabase).
//
// The wizard has no sign-up of its own: a participant makes an account in the
// demo, the demo's administrators approve it, and the same address and password
// open the wizard. Everything here is read when a request comes in, not when the
// image is built, so one image serves Rahti, Azure and a local stack.

import type { SupabaseClient } from "@supabase/supabase-js";
import { gaikDemoUrl } from "@/lib/gaik-demo";
import { DEV_AUTH, isAllowedEmail, type AuthUser } from "@/lib/auth";

/** Whether the instance signs its users in through Supabase (WIZARD_AUTH_MODE=supabase). */
export function supabaseAuthEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return env.WIZARD_AUTH_MODE?.trim() === "supabase";
}

/**
 * Whether the dev login is the one in use. An image built with
 * NEXT_PUBLIC_DEV_AUTH=true runs without it when WIZARD_AUTH_MODE=supabase, as
 * it does behind the sign-in proxy: a dev cookie then signs nobody in.
 */
export function devAuthActive(env: NodeJS.ProcessEnv = process.env): boolean {
  return DEV_AUTH && !supabaseAuthEnabled(env);
}

// Written out in full so Next.js puts the build's values in: it replaces only a
// literal process.env.NEXT_PUBLIC_*, and the image's runner stage does not carry
// them as environment variables.
const BUILT_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const BUILT_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

/**
 * The Supabase project's address and public key. `WIZARD_SUPABASE_URL` and
 * `WIZARD_SUPABASE_KEY` are read at run time; the build-time `NEXT_PUBLIC_*`
 * pair is the fallback for an image built for one project. Never a secret or
 * service-role key: that one passes the table rules by, and the wizard only
 * reads what a user may read of their own.
 */
export function supabaseSettings(
  env: NodeJS.ProcessEnv = process.env,
): { url: string; key: string } | null {
  const url =
    env.WIZARD_SUPABASE_URL?.trim() || env.NEXT_PUBLIC_SUPABASE_URL?.trim() || BUILT_URL?.trim();
  const key =
    env.WIZARD_SUPABASE_KEY?.trim() ||
    env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim() ||
    BUILT_KEY?.trim();
  return url && key ? { url, key } : null;
}

/**
 * Where a person without an account makes one: `WIZARD_SUPABASE_SIGNUP_URL`, or
 * the demo's own sign-up page. Only an http(s) address is used; an empty value
 * hides the link.
 */
export function supabaseSignUpUrl(env: NodeJS.ProcessEnv = process.env): string | null {
  const raw = env.WIZARD_SUPABASE_SIGNUP_URL;
  if (raw !== undefined) {
    const value = raw.trim();
    if (!value) return null;
    try {
      const url = new URL(value);
      return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
    } catch {
      return null;
    }
  }
  const demo = gaikDemoUrl(env.GAIK_DEMO_URL);
  // Under the demo's own path: "https://host/demo" gives ".../demo/sign-up".
  return demo ? new URL("sign-up", demo.endsWith("/") ? demo : `${demo}/`).href : null;
}

/** Whether access is taken from the demo's access_requests table (WIZARD_SUPABASE_ACCESS). */
export function accessRequestsEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return env.WIZARD_SUPABASE_ACCESS?.trim() === "access_requests";
}

/** The part of a demo access_requests row the wizard reads. */
export type AccessRow = { status?: string | null; wizard_access?: boolean | null };

/**
 * A row lets its user in only when the demo has approved it. ``wizard_access``
 * is the demo's grant for its first wizard, given on top of approval; on its own
 * (a pending or rejected row) it opens nothing, as in the demo.
 */
export function rowGrantsAccess(row: AccessRow | null | undefined): boolean {
  return row?.status === "approved";
}

/** A signed-in Supabase user, with the id their access_requests row is keyed by. */
export type SupabaseUser = AuthUser & { id?: string };

/**
 * Whether a signed-in Supabase user may use the wizard. The address must be
 * confirmed: until Supabase has confirmed it, it is only a claim. Then either
 * it is in WIZARD_ALLOWED_EMAILS, or, with WIZARD_SUPABASE_ACCESS=access_requests,
 * the user's own row in the demo's table is approved. The row is read with the
 * user's own session, so the table's rules decide what can be read; a missing
 * row, or one that cannot be read, lets nobody in.
 */
export async function hasWizardAccess(
  supabase: Pick<SupabaseClient, "from">,
  user: SupabaseUser | null | undefined,
  env: NodeJS.ProcessEnv = process.env,
  now: number = Date.now(),
): Promise<boolean> {
  if (!user?.email_confirmed_at || !user.email) return false;
  if (isAllowedEmail(user.email, env)) return true;
  if (!accessRequestsEnabled(env) || !user.id) return false;
  if ((granted.get(user.id) ?? 0) > now) return true;
  try {
    const { data, error } = await supabase
      .from("access_requests")
      .select("status, wizard_access")
      .eq("user_id", user.id)
      .maybeSingle();
    const allowed = !error && rowGrantsAccess(data as AccessRow | null);
    if (allowed) remember(user.id, now, accessCacheMs(env));
    return allowed;
  } catch {
    return false;
  }
}

/**
 * How long an approval is taken as read, in ms: WIZARD_SUPABASE_ACCESS_CACHE_S
 * (default 60, 0 is off). A page and its polling ask for the row on every
 * request, the proxy and the page once each; without this, a full room asks
 * the demo's project many times a second. Only an approval is kept: a waiting
 * account sees its approval at once, and a withdrawn one ends within the time.
 */
export function accessCacheMs(env: NodeJS.ProcessEnv = process.env): number {
  const raw = env.WIZARD_SUPABASE_ACCESS_CACHE_S?.trim();
  if (!raw) return 60_000;
  const seconds = Number(raw);
  return Number.isFinite(seconds) && seconds >= 0 ? Math.min(seconds, 3600) * 1000 : 60_000;
}

/** User id -> when the approval read for them stops counting (ms since the epoch). */
const granted = new Map<string, number>();
const MAX_REMEMBERED = 5000;

function remember(userId: string, now: number, ttl: number): void {
  if (ttl <= 0) return;
  if (granted.size >= MAX_REMEMBERED) {
    for (const [id, until] of granted) if (until <= now) granted.delete(id);
    if (granted.size >= MAX_REMEMBERED) granted.clear();
  }
  granted.set(userId, now + ttl);
}

/** For tests: forget every approval read so far. */
export function forgetAccessReads(): void {
  granted.clear();
}
