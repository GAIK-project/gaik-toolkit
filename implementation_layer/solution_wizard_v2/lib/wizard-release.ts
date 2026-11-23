/**
 * Whether the wizard held for a finished session has been released by this
 * browser, so the page asks for it once per finish and not on every load.
 *
 * A live wizard is a process on the server, and they are few. The page
 * releases it when the last gate is approved (components/release-wizard) and
 * remembers that here. The mark lasts only as long as the session stays
 * finished: the next message starts the wizard again, and when the last gate
 * is reopened and approved a second time the wizard has to be released a
 * second time. The mark was kept for good, so that second release never came
 * and the wizard held its slot until the idle cleanup. A page that shows the
 * session not finished takes the mark away (forgetReleased).
 */

const storageKey = (sessionId: string) => `wizard-released:${sessionId}`;
/** Sessions released, or being released, in this page load: also for a browser with no storage. */
const settled = new Set<string>();
/** How many times each session's mark has been taken away in this page load. */
const forgotten = new Map<string, number>();

/** True once the wizard of this finish has been released, or is being released now. */
export function alreadyReleased(sessionId: string): boolean {
  if (settled.has(sessionId)) return true;
  try {
    return window.localStorage.getItem(storageKey(sessionId)) !== null;
  } catch {
    return false;
  }
}

/**
 * A release has been asked for: a second one is not sent meanwhile. Returns
 * what rememberReleased needs to tell whether the answer is still about this
 * finish.
 */
export function releaseStarted(sessionId: string): number {
  settled.add(sessionId);
  return forgotten.get(sessionId) ?? 0;
}

/** The release did not happen (the wizard was replying, the request failed): it is asked again later. */
export function releaseFailed(sessionId: string): void {
  settled.delete(sessionId);
}

/**
 * The wizard is released: remembered for the next load of the finished
 * session. Not when the session was seen not finished after the release was
 * asked for (`started`, from releaseStarted): the answer is then about an
 * earlier finish, and the next one has its own release.
 */
export function rememberReleased(sessionId: string, started?: number): void {
  if (started !== undefined && started !== (forgotten.get(sessionId) ?? 0)) return;
  settled.add(sessionId);
  try {
    window.localStorage.setItem(storageKey(sessionId), "1");
  } catch {
    // No storage: remembered until the page is loaded again.
  }
}

/** The session is not finished (any more): its next finish releases the wizard again. */
export function forgetReleased(sessionId: string): void {
  settled.delete(sessionId);
  forgotten.set(sessionId, (forgotten.get(sessionId) ?? 0) + 1);
  try {
    window.localStorage.removeItem(storageKey(sessionId));
  } catch {
    // No storage: there was only the mark in memory.
  }
}
