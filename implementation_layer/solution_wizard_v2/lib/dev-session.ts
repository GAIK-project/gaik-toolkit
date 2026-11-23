// Signed dev-login session (review P5).
//
// The dev cookie used to hold the bare e-mail: anyone could set
// `gaik_dev_session=dev@gaik.local` in their browser and be signed in, on any
// instance built with NEXT_PUBLIC_DEV_AUTH=true — the Rahti stacks included.
// The value is now `email|expiry|HMAC-SHA256(email|expiry)`, so a cookie that
// was not issued by this server (or has expired) is just not a session.
//
// Web Crypto only: this runs in the proxy (proxy.ts) as well as in Server
// Actions and route handlers, and Web Crypto is there in all of them.

import { isDevUserEmail } from "@/lib/auth";

export const DEV_SESSION_MAX_AGE_S = 12 * 60 * 60;

// Signing key, in order of preference. The Server Actions key is already a
// per-deployment secret on every stack (compose, Rahti), so a signed cookie
// needs no new configuration there; DEV_AUTH_SECRET exists for setting one
// separately. Without either, a public fallback keeps a bare local checkout
// working — and says so, because then the cookie is forgeable again. A
// production build has no fallback: there a missing key means nobody is
// signed in, rather than anyone being able to sign a cookie.
const FALLBACK_SECRET = "gaik-dev-auth-local-fallback-not-a-secret";
let warnedAboutKey = false;

function warnOnce(message: string, log: (message: string) => void): void {
  if (warnedAboutKey) return;
  warnedAboutKey = true;
  log(message);
}

function signingSecret(): string | null {
  const configured =
    process.env.DEV_AUTH_SECRET?.trim() || process.env.NEXT_SERVER_ACTIONS_ENCRYPTION_KEY?.trim();
  if (configured) return configured;
  if (process.env.NODE_ENV === "production") {
    warnOnce(
      "[dev-auth] Neither DEV_AUTH_SECRET nor NEXT_SERVER_ACTIONS_ENCRYPTION_KEY is set: " +
        "dev sign-in is disabled until one of them is.",
      console.error,
    );
    return null;
  }
  warnOnce(
    "[dev-auth] Neither DEV_AUTH_SECRET nor NEXT_SERVER_ACTIONS_ENCRYPTION_KEY is set: " +
      "dev session cookies are signed with a public fallback key and can be forged. " +
      "Set one of them in any deployed environment.",
    console.warn,
  );
  return FALLBACK_SECRET;
}

function base64url(bytes: Uint8Array): string {
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function hmac(secret: string, message: string): Promise<string> {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(message));
  return base64url(new Uint8Array(signature));
}

function constantTimeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/** The cookie value for a dev user who just proved their password. */
export async function signDevSession(email: string, now: number = Date.now()): Promise<string> {
  const secret = signingSecret();
  if (!secret) throw new Error("Dev sign-in is disabled: no session signing key is configured.");
  const expires = Math.floor(now / 1000) + DEV_SESSION_MAX_AGE_S;
  const payload = `${email}|${expires}`;
  return `${payload}|${await hmac(secret, payload)}`;
}

/**
 * The dev user a cookie value stands for, or null: missing, malformed, not a
 * dev account, expired, or not signed by this server. A bare e-mail — the
 * old, forgeable format — is null too, and so is every cookie on a production
 * build that has no signing key.
 */
export async function verifyDevSession(
  value: string | undefined,
  now: number = Date.now(),
): Promise<string | null> {
  if (!value) return null;
  const parts = value.split("|");
  if (parts.length !== 3) return null;
  const [email, expiresText, signature] = parts;
  if (!isDevUserEmail(email)) return null;
  const expires = Number(expiresText);
  if (!Number.isFinite(expires) || expires * 1000 <= now) return null;
  const secret = signingSecret();
  if (!secret) return null;
  const expected = await hmac(secret, `${email}|${expiresText}`);
  return constantTimeEqual(signature, expected) ? email : null;
}
