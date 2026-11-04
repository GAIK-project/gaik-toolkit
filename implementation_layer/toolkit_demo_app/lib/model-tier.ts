import {
  ADMIN_COOKIE_NAME,
  verifyAdminSessionValue,
} from "@/lib/admin/session";

/** Sent by the proxy to the API, never by the browser: the API trusts it. */
export const MODEL_TIER_HEADER = "x-gaik-model-tier";

const STAFF_DOMAIN = "@haaga-helia.fi";

/**
 * The GAIK team may run the costlier server models: the admin, the shared demo
 * account (DEMO_USER_NAME) and haaga-helia.fi addresses.
 */
export function isModelStaff(
  email: string | null,
  adminCookie: string | undefined,
): boolean {
  if (verifyAdminSessionValue(adminCookie)) return true;
  if (!email) return false;
  const demoUser = process.env.DEMO_USER_NAME?.trim().toLowerCase();
  if (demoUser && email === demoUser) return true;
  return email.endsWith(STAFF_DOMAIN);
}

export { ADMIN_COOKIE_NAME };
