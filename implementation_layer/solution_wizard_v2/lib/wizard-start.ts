/**
 * When the chat says that the wizard is starting, not thinking.
 *
 * A wizard is a process on the server, held for a session while it is in use
 * and released after a break (30 idle minutes, a finished session, a restart
 * of the server). The next message starts it again, and it reads the session
 * before it answers, which takes a while. wizard_api answers the message
 * (the reply's stream opens) only once the wizard is up, so two things tell:
 * the session as the page read it says that no wizard is held for it, or the
 * answer to a message is late.
 */

/** The answer of a held wizard opens well inside this; a longer wait is a start. */
export const STARTING_AFTER_MS = 3000;

/**
 * How long after a message is sent the waiting line says that the wizard is
 * starting, in ms. `live` is whether a wizard is held for the session, as far
 * as the page knows: false says so at once, and anything else (held, or not
 * known, as in the store without wizard_api) only when the answer is late.
 */
export function startingLineDelay(live: boolean | null | undefined): number {
  return live === false ? 0 : STARTING_AFTER_MS;
}
