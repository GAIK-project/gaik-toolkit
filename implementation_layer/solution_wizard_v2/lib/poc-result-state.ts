/**
 * Whether the test result on the PoC tab still describes the package that is
 * there, and what a run said about its own result.
 *
 * Gate 3 approves a test run. A run that had succeeded stayed "succeeded" on
 * the page while the wizard rewrote the package behind it, and the gate could
 * be approved on a result the current package had never produced.
 *
 * Two things say a result is of another package:
 *
 * - wizard_api's own record: the digest of the package the successful run was
 *   started on (the session's `last_successful_run_package`) against the
 *   digest of the package as it is now (`package_digest` of the package's file
 *   list). This is what the api refuses Gate 3 on, it is there after a reload
 *   and the session page can read it on any tab;
 * - what the PoC tab saw happen while it was open: the wizard is replying, or
 *   the package's version changed after the run it followed.
 */

/**
 * True when the run that passed tested another package than the one that is
 * there now, by wizard_api's digests. A digest that is missing (an api that
 * keeps none, a run recorded before it did, no package) is never held against
 * the result.
 */
export function packageChangedSinceRun(
  packageDigest: string | null | undefined,
  testedDigest: string | null | undefined,
): boolean {
  return Boolean(packageDigest) && Boolean(testedDigest) && packageDigest !== testedDigest;
}

export type ResultStaleInput = {
  /** The wizard is replying: it may be rewriting the package. */
  wizardReplying: boolean;
  /** A reply has ended and the package has not been read again since. */
  packageStale: boolean;
  /** Version of the package that is there now; null where the api gives none (the mock). */
  packageVersion: string | null;
  /** The package version the result ran on; null when the page cannot tell. */
  resultVersion: string | null;
  /** wizard_api's digest of the package as it is now; null where it gives none. */
  packageDigest?: string | null;
  /** That digest for the run recorded as successful; null where none is kept. */
  testedDigest?: string | null;
};

/**
 * True while the result is, or may be, that of an earlier package. A version
 * or digest the page does not know (the mock store, an api that keeps no
 * digest, a run from before the page was loaded) is not held against the
 * result. It is over when a run of the package that is there has succeeded.
 */
export function resultIsStale(input: ResultStaleInput): boolean {
  if (input.wizardReplying || input.packageStale) return true;
  if (packageChangedSinceRun(input.packageDigest, input.testedDigest)) return true;
  return (
    input.packageVersion !== null && input.resultVersion !== null && input.packageVersion !== input.resultVersion
  );
}

/**
 * Whether Gate 3's approval waits. The PoC tab's word counts while it holds
 * the api's digests (`packageRead`): it reads the package again after every
 * run and reply, so it knows of a new successful run before the page does.
 * Until it has read them (another tab is open, the answer is on its way) the
 * page's own reading of the digests stands, so the approval is held from the
 * first paint and on every tab.
 */
export function gate3Waits(
  tab: { stale: boolean; packageRead: boolean },
  /** The session page's reading: the package changed after the successful run. */
  pageSaysChanged: boolean,
): boolean {
  return tab.stale || (!tab.packageRead && pageSaysChanged);
}

export type RunWarning = {
  code: string;
  message: string;
  /** The 1-based numbers of the records the warning is about; empty when the api names none. */
  records: number[];
  /** The output field it is about, for a warning about one field. */
  field?: string;
};

/**
 * The `warnings` of a run-output answer: what the run finished with that the
 * user should look at before trusting the result. An answer without the field
 * (an api that does not send it yet), or with an empty list, has none.
 */
export function runWarnings(raw: unknown): RunWarning[] {
  if (typeof raw !== "object" || raw === null) return [];
  const list = (raw as { warnings?: unknown }).warnings;
  if (!Array.isArray(list)) return [];
  const warnings: RunWarning[] = [];
  for (const item of list) {
    if (typeof item !== "object" || item === null) continue;
    const { code, message, records, field } = item as {
      code?: unknown;
      message?: unknown;
      records?: unknown;
      field?: unknown;
    };
    if (typeof message !== "string" || !message.trim()) continue;
    warnings.push({
      code: typeof code === "string" ? code : "",
      message: message.trim(),
      records: Array.isArray(records) ? records.filter((n): n is number => Number.isInteger(n)) : [],
      ...(typeof field === "string" && field ? { field } : {}),
    });
  }
  return warnings;
}

/**
 * What the PoC tab's last step ("use the solution") is about:
 *
 * - `no_package`: there is nothing to use yet;
 * - `locked`: a package, and no run recorded as successful for it;
 * - `check`: a run is recorded and the run in view finished with warnings, so
 *   the step does not call it a success and the download is not its first action;
 * - `ready`: a run is recorded and nothing in view says to check it.
 *
 * Warnings inform, they do not block: the download is there in `check` too.
 */
export type HandoverState = "no_package" | "locked" | "check" | "ready";

export function handoverState(input: {
  packageReady: boolean;
  /** wizard_api has a successful run on record. */
  runRecorded: boolean;
  /** The run in view succeeded and its output answer carried warnings. */
  shownRunHasWarnings: boolean;
}): HandoverState {
  if (!input.packageReady) return "no_package";
  if (!input.runRecorded) return "locked";
  return input.shownRunHasWarnings ? "check" : "ready";
}

// The PoC tab knows whether the result is stale; the gate's approve buttons
// (the bar under the workspace, the one under the wizard's reply) are drawn
// elsewhere on the page. The tab says it here and they read it, whichever of
// them is drawn first.
const staleBySession = new Map<string, boolean>();
const packageReadBySession = new Map<string, boolean>();
const warningsBySession = new Map<string, boolean>();
const listeners = new Set<() => void>();

/**
 * The workspace's word on the run it shows: it succeeded and its output answer
 * carried warnings. The session page has the run's id and not its output, so
 * the finished solution's banner reads this instead of asking for the output
 * a second time. False when the workspace goes away.
 */
export function publishRunWarnings(sessionId: string, hasWarnings: boolean): void {
  if ((warningsBySession.get(sessionId) ?? false) === hasWarnings) return;
  if (hasWarnings) warningsBySession.set(sessionId, true);
  else warningsBySession.delete(sessionId);
  for (const listener of listeners) listener();
}

/** Whether the run the workspace shows finished with warnings; told through subscribeResultStale. */
export function runWarningsFor(sessionId: string): boolean {
  return warningsBySession.get(sessionId) ?? false;
}

/**
 * The PoC tab's word on its result; false when the tab goes away.
 * `packageRead` says the tab holds the api's digests for that word (see
 * gate3Waits).
 */
export function publishResultStale(sessionId: string, stale: boolean, packageRead = false): void {
  const same =
    (staleBySession.get(sessionId) ?? false) === stale &&
    (packageReadBySession.get(sessionId) ?? false) === packageRead;
  if (same) return;
  if (stale) staleBySession.set(sessionId, true);
  else staleBySession.delete(sessionId);
  if (packageRead) packageReadBySession.set(sessionId, true);
  else packageReadBySession.delete(sessionId);
  for (const listener of listeners) listener();
}

export function subscribeResultStale(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function resultStaleFor(sessionId: string): boolean {
  return staleBySession.get(sessionId) ?? false;
}

/** Whether the PoC tab holds the api's digests of the session's package now. */
export function packageReadFor(sessionId: string): boolean {
  return packageReadBySession.get(sessionId) ?? false;
}
