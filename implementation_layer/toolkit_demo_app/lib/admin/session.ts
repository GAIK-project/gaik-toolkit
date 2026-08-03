import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";

export const ADMIN_COOKIE_NAME = "admin_session";
export const ADMIN_SESSION_MAX_AGE_SECONDS = 60 * 60 * 8; // 8 hours

/**
 * Secret used to sign admin session cookies. Prefer a dedicated
 * `ADMIN_SESSION_SECRET`; fall back to `ADMIN_PASSWORD` so an existing
 * deployment keeps working without a new env var. Read at call time so
 * container env changes take effect without a rebuild.
 */
function sessionSecret(): string | null {
  return process.env.ADMIN_SESSION_SECRET || process.env.ADMIN_PASSWORD || null;
}

function sign(payload: string, secret: string): string {
  return createHmac("sha256", secret).update(payload).digest("base64url");
}

/**
 * Mint a signed session value: `<expiresAtMs>.<nonce>.<hmac>`. The nonce makes
 * two sessions issued in the same millisecond distinct; the HMAC is what makes
 * the cookie unforgeable without the secret.
 */
export function createAdminSessionValue(): string | null {
  const secret = sessionSecret();
  if (!secret) return null;
  const expiresAt = Date.now() + ADMIN_SESSION_MAX_AGE_SECONDS * 1000;
  const payload = `${expiresAt}.${randomBytes(12).toString("base64url")}`;
  return `${payload}.${sign(payload, secret)}`;
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
  const secret = sessionSecret();
  if (!secret || !raw) return false;

  const split = raw.lastIndexOf(".");
  if (split <= 0) return false;
  const payload = raw.slice(0, split);
  const signature = raw.slice(split + 1);

  if (!signatureMatches(signature, sign(payload, secret))) return false;

  const expiresAt = Number(payload.slice(0, payload.indexOf(".")));
  return Number.isFinite(expiresAt) && Date.now() < expiresAt;
}

/** Cookie-reading wrapper around {@link verifyAdminSessionValue}. */
export async function isAdminAuthenticated(): Promise<boolean> {
  return verifyAdminSessionValue((await cookies()).get(ADMIN_COOKIE_NAME)?.value);
}
