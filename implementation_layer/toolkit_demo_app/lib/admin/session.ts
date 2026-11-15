import {
  createHash,
  createHmac,
  randomBytes,
  scryptSync,
  timingSafeEqual,
} from "node:crypto";
import { cookies } from "next/headers";

export const ADMIN_COOKIE_NAME = "admin_session";
export const ADMIN_SESSION_MAX_AGE_SECONDS = 60 * 60 * 8; // 8 hours

// The admin dashboard has one shared password until the demo gets named
// accounts with the organisation's sign-in, planned for after the AI Hackathon
// (3 December 2026). Until then the password is compared in constant time,
// sign-in attempts are limited (lib/admin/sign-in-limit.ts), the cookie is
// signed with a key of its own, and every admin action is logged with the
// session it came from (app/admin/actions.ts).

const DERIVED_KEY_LABEL = "gaik-demo-admin-session-v1";
let derived: { password: string; key: Buffer } | null = null;

/**
 * Key used to sign admin session cookies: `ADMIN_SESSION_SECRET` when set.
 * Without it the key is derived from `ADMIN_PASSWORD` with scrypt, so the
 * password itself never signs a cookie. The derivation is cached per password
 * value. Read at call
 * time so container env changes take effect without a rebuild.
 */
function sessionKey(): Buffer | string | null {
  const secret = process.env.ADMIN_SESSION_SECRET;
  if (secret) return secret;
  const password = process.env.ADMIN_PASSWORD;
  if (!password) return null;
  if (derived?.password !== password)
    derived = {
      password,
      key: scryptSync(password, DERIVED_KEY_LABEL, 32, {
        N: 2 ** 15,
        maxmem: 64 * 1024 * 1024,
      }),
    };
  return derived.key;
}

function sign(payload: string, key: Buffer | string): string {
  return createHmac("sha256", key).update(payload).digest("base64url");
}

/**
 * True when `given` is the configured admin password. Both sides are hashed
 * first, so the comparison takes the same time whatever their lengths.
 */
export function adminPasswordMatches(given: string): boolean {
  const expected = process.env.ADMIN_PASSWORD;
  if (!expected) return false;
  const digest = (s: string) => createHash("sha256").update(s).digest();
  return timingSafeEqual(digest(given), digest(expected));
}

/**
 * Mint a signed session value: `<expiresAtMs>.<nonce>.<hmac>`. The nonce makes
 * two sessions issued in the same millisecond distinct and names the session in
 * the admin action log; the HMAC is what makes the cookie unforgeable without
 * the key.
 */
export function createAdminSessionValue(): string | null {
  const key = sessionKey();
  if (!key) return null;
  const expiresAt = Date.now() + ADMIN_SESSION_MAX_AGE_SECONDS * 1000;
  const payload = `${expiresAt}.${randomBytes(12).toString("base64url")}`;
  return `${payload}.${sign(payload, key)}`;
}

function signatureMatches(actual: string, expected: string): boolean {
  const a = Buffer.from(actual);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

/**
 * True only for a value this server signed and that has not expired. Rejects
 * anything a client could construct on its own — including the legacy constant
 * `authenticated` value, which had no signature at all.
 */
export function verifyAdminSessionValue(raw: string | undefined): boolean {
  if (!raw) return false;
  const key = sessionKey();
  if (!key) return false;

  const split = raw.lastIndexOf(".");
  if (split <= 0) return false;
  const payload = raw.slice(0, split);
  const signature = raw.slice(split + 1);

  if (!signatureMatches(signature, sign(payload, key))) return false;

  const expiresAt = Number(payload.slice(0, payload.indexOf(".")));
  return Number.isFinite(expiresAt) && Date.now() < expiresAt;
}

/**
 * A short name for a verified session, for the admin action log: the first
 * characters of its nonce. Null for a value that does not verify.
 */
export function adminSessionId(raw: string | undefined): string | null {
  if (!raw || !verifyAdminSessionValue(raw)) return null;
  return raw.split(".")[1]?.slice(0, 8) ?? null;
}

/** Cookie-reading wrapper around {@link verifyAdminSessionValue}. */
export async function isAdminAuthenticated(): Promise<boolean> {
  return verifyAdminSessionValue((await cookies()).get(ADMIN_COOKIE_NAME)?.value);
}

/** The session id of the signed-in admin, or null (see {@link adminSessionId}). */
export async function currentAdminSessionId(): Promise<string | null> {
  return adminSessionId((await cookies()).get(ADMIN_COOKIE_NAME)?.value);
}
