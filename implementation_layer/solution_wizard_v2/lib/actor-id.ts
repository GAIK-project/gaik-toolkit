import { createHash, createHmac } from "node:crypto";
import { logger } from "@/lib/logger";

// A stable pseudonym for the signed-in user in logs and audit events.
//
// The log line used to carry the e-mail address itself. An operator still
// needs to tell one person's actions apart from another's (and from the same
// person across requests), but the address has no business sitting in the
// log stream, where it is kept and forwarded far longer than the session.
// So the e-mail is folded into `u_` + the first 16 hex chars of an HMAC-SHA256
// over the lowercased, trimmed address: the same person always gets the same
// id, and the id alone does not give the address back.
//
// Key, in order of preference: WIZARD_PSEUDONYM_KEY, or the Server Actions
// key that every deployment already has (with a label in the HMAC input so
// the pseudonym is not a signature made with that key). Without either, a
// plain SHA-256 keeps the id stable but guessable for anyone who knows an
// address, and the first use says so once.
//
// node:crypto only: this runs in route handlers and Server Actions, not in
// the Edge middleware.

const DOMAIN = "gaik-wizard-actor-id-v1";
let warnedUnkeyed = false;

export function normaliseEmail(email: string): string {
  return email.trim().toLowerCase();
}

/** The key for actor and owner ids; changing it gives everyone new ids. */
export function pseudonymKey(): string | null {
  return process.env.WIZARD_PSEUDONYM_KEY?.trim() || process.env.NEXT_SERVER_ACTIONS_ENCRYPTION_KEY?.trim() || null;
}

/** A short, stable identifier for `email` that is safe to write into a log line. */
export function actorId(email: string): string {
  const key = pseudonymKey();
  let digest: string;
  if (key) {
    digest = createHmac("sha256", key).update(`${DOMAIN}:${normaliseEmail(email)}`).digest("hex");
  } else {
    if (!warnedUnkeyed) {
      warnedUnkeyed = true;
      logger.warn(
        "[actor-id] Neither WIZARD_PSEUDONYM_KEY nor NEXT_SERVER_ACTIONS_ENCRYPTION_KEY is set: " +
          "actor pseudonyms in logs are an unkeyed hash of the address. Set one of them in any deployed environment.",
      );
    }
    digest = createHash("sha256").update(`${DOMAIN}:${normaliseEmail(email)}`).digest("hex");
  }
  return `u_${digest.slice(0, 16)}`;
}

/** Test hook: forget that the unkeyed warning was already given. */
export function resetActorIdWarningForTests(): void {
  warnedUnkeyed = false;
}
