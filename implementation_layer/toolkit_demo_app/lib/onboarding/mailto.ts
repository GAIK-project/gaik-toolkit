/**
 * Contact details + a prefilled "request Solution Wizard access" email.
 *
 * The Wizard is a gated beta with no self-serve unlock: a prospective tester
 * reaches the GAIK team with a short company intro and their use case, and an
 * admin grants `wizard_access` (see proxy.ts and /admin).
 */

/** GAIK research & development contact (also shown on the privacy page). */
export const GAIK_CONTACT_EMAIL = "dmitry.kudryavtsev@haaga-helia.fi";

/** Public contact page on the GAIK site. */
export const GAIK_CONTACT_URL = "https://gaik.ai/contact-info/";

const SUBJECT = "GAIK Solution Wizard — beta access request";

const BODY = [
  "Hi GAIK team,",
  "",
  "I'd like to try the Solution Configuration Wizard. A short introduction:",
  "",
  "• Company / organisation: ",
  "• My role: ",
  "• Use case I'd like to configure: ",
  "",
  "Thanks!",
].join("\n");

/** `mailto:` href that opens a prefilled access-request email. */
export function buildAccessRequestMailto(): string {
  const query = `subject=${encodeURIComponent(SUBJECT)}&body=${encodeURIComponent(BODY)}`;
  return `mailto:${GAIK_CONTACT_EMAIL}?${query}`;
}
