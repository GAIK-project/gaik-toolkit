import { createHash, createHmac } from "node:crypto";
import { normaliseEmail, pseudonymKey } from "@/lib/actor-id";

// The id that owns a user's wizard sessions in wizard_api.
//
// wizard_api keys every session on its owner: the session row, the folder its
// files are kept in, the sandbox Job's labels and the ownership check on each
// request. That key used to be the e-mail address. Now the web app sends
// `o_` + the first 32 hex chars of an HMAC-SHA256 over the lowercased, trimmed
// address instead, so wizard_api, its database and the session folders never
// hold the address.
//
// The key is the one the log pseudonym uses (`lib/actor-id.ts`), with its own
// label, so the owner id and the actor id differ. Changing the key gives every
// user a new owner id, and the sessions under the old ids no longer show up:
// set the key once per deployment and keep it. wizard_api computes the same id
// in `wizard_api/owner_id.py` for its admin commands; a shared test vector
// keeps the two in step.

const DOMAIN = "gaik-wizard-owner-id-v1";
export const OWNER_ID_PATTERN = /^o_[0-9a-f]{32}$/;

/** The owner id for `email`: stable per person and deployment, without the address. */
export function ownerId(email: string): string {
  const key = pseudonymKey();
  const input = `${DOMAIN}:${normaliseEmail(email)}`;
  const digest = key
    ? createHmac("sha256", key).update(input).digest("hex")
    : createHash("sha256").update(input).digest("hex");
  return `o_${digest.slice(0, 32)}`;
}
