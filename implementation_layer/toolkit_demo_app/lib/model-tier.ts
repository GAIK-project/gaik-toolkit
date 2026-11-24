import {
  ADMIN_COOKIE_NAME,
  verifyAdminSessionValue,
} from "@/lib/admin/session";

/** Sent by the proxy to the API, never by the browser: the API trusts it. */
export const MODEL_TIER_HEADER = "x-gaik-model-tier";

const STAFF_DOMAIN = "@haaga-helia.fi";

// The chat models everyone signed in may run on the server's credentials; every
// other model is for the team. The API reads the same DEMO_OPEN_MODELS
// (api/utils/model_settings.py), so set it on both deployments.
const OPEN_MODELS = "gpt-6-luna,claude-haiku-5-5";

export function openModels(): string[] {
  return (process.env.DEMO_OPEN_MODELS ?? OPEN_MODELS)
    .split(",")
    .map((name) => name.trim())
    .filter(Boolean);
}

/**
 * The Azure deployment a demo that runs its model in Next.js uses for this user:
 * the configured one for the team or when it is open, else the first open GPT model.
 */
export function deploymentFor(configured: string, staff: boolean): string {
  const open = openModels();
  if (staff || open.includes(configured)) return configured;
  return open.find((name) => name.startsWith("gpt-")) ?? configured;
}

/**
 * The GAIK team may run every server model; everyone else the open ones
 * (openModels). The team: the admin, the shared demo account (DEMO_USER_NAME),
 * haaga-helia.fi addresses and anyone listed in MODEL_STAFF_EMAILS
 * (comma-separated, set on the deployment, not in the repo).
 */
export function isModelStaff(
  email: string | null,
  adminCookie: string | undefined,
): boolean {
  if (verifyAdminSessionValue(adminCookie)) return true;
  if (!email) return false;
  const demoUser = process.env.DEMO_USER_NAME?.trim().toLowerCase();
  if (demoUser && email === demoUser) return true;
  const listed = (process.env.MODEL_STAFF_EMAILS ?? "")
    .split(",")
    .map((entry) => entry.trim().toLowerCase())
    .filter(Boolean);
  if (listed.includes(email)) return true;
  return email.endsWith(STAFF_DOMAIN);
}

export { ADMIN_COOKIE_NAME };
