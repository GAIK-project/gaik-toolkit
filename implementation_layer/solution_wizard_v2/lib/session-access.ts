import { getCurrentUser } from "@/lib/current-user";
import { claimLegacySessions, getSession, sessionOwnerFor, type WizardSession } from "@/lib/sessions";
import { audit } from "@/lib/audit";

/**
 * Load a session only if it belongs to the signed-in user (US-S1-01 isolation).
 * `email` is the signed-in user's address; wizard_api keeps sessions under its owner
 * id (`lib/owner-id.ts`). Returns undefined when missing or owned by another user.
 */
export async function getSessionForUser(
  sessionId: string,
  email: string,
): Promise<WizardSession | undefined> {
  await claimLegacySessions(email);
  const session = await getSession(sessionId);
  if (!session) return undefined;
  if (session.userId !== sessionOwnerFor(email)) {
    // The meaningful security case: an authenticated user reaching for a
    // session that isn't theirs, not just "not logged in" (see
    // requireOwnedSession, which doesn't audit that path — it's the default
    // anonymous-visitor case, not an access-control violation).
    audit("auth.denied", {
      actor: email,
      resource: { type: "session", id: sessionId },
      outcome: "denied",
      reason: "not_owner",
    });
    return undefined;
  }
  return session;
}

/** Current user + owned session, or null if denied. */
export async function requireOwnedSession(
  sessionId: string,
): Promise<{ user: { email: string }; session: WizardSession } | null> {
  const user = await getCurrentUser();
  if (!user) return null;
  const session = await getSessionForUser(sessionId, user.email);
  if (!session) return null;
  return { user, session };
}
