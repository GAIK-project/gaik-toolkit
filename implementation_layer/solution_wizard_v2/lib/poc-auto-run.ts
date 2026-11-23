import type { PackageStatus } from "./poc-preflight";

/**
 * Whether the PoC tab starts a test run by itself now.
 *
 * The run was a button: the package was ready and checked, the test material
 * was there, and the session still waited for someone to press "Run the test"
 * before there was anything to look at. Users asked why that step was theirs.
 * The run now starts when everything it needs is in place, and again when the
 * wizard has changed the package, so the user's part is to judge the result.
 * "Run again" stays, for a run on the user's own material.
 *
 * A run is started once per package version. A session opened with a run
 * already behind it takes that run as its package's ("adopt"): the page cannot
 * tell which version the run tested, and starting another on every reload
 * would spend the shared sandbox for nothing.
 */
export type AutoRunInput = {
  onPocTab: boolean;
  /** Gate 2 is approved: the api refuses a run before it. */
  gateApproved: boolean;
  /** The wizard is replying, so it may still be writing the package. */
  wizardReplying: boolean;
  /** "ready" is a complete package whose check passed. */
  packageStatus: PackageStatus;
  /** Digest of the package's files; null where the api gives none (the mock). */
  version: string | null;
  /** The user's own test material is in the package (see userInputs). */
  hasInput: boolean;
  /** A run or a package generation is going in this view. */
  busy: boolean;
  /** The version the last run started on, as far as this page knows; null when none. */
  ranVersion: string | null;
  /** The session had a run before this page was loaded, or one was started here. */
  hasEarlierRun: boolean;
  /**
   * The package version that was there when a gate was reopened, while that
   * gate still waits: the change the gate was reopened for has not reached
   * the package yet, so a run would test what was already tested.
   */
  heldVersion?: string | null;
};

/** One file in the package's sample_input/, as the PoC tab lists it. */
export type PocInputFile = { name: string; bytes: number; uploaded?: boolean };

/**
 * The files the user added themselves. The wizard writes example inputs into
 * the same folder; a run started by itself on those (a UC04 session) tested
 * the wizard's examples before the user had added anything, and the report
 * cited them beside the user's documents. A listing without the flag (the
 * mock store, an older api) counts every file as the user's, as before.
 */
export function userInputs(files: PocInputFile[]): PocInputFile[] {
  return files.filter((f) => f.uploaded !== false);
}

export function autoRunDecision(input: AutoRunInput): "run" | "adopt" | "wait" {
  if (!input.onPocTab || !input.gateApproved || input.wizardReplying || input.busy) return "wait";
  if (input.packageStatus !== "ready" || input.version === null) return "wait";
  if (input.ranVersion === input.version) return "wait";
  if (input.ranVersion === null && input.hasEarlierRun) return "adopt";
  if (input.heldVersion != null && input.heldVersion === input.version) return "wait";
  if (!input.hasInput) return "wait";
  return "run";
}
