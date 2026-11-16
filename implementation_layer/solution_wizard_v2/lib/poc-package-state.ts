/**
 * What the PoC tab knows about the generated package.
 *
 * wizard_api's `GET /sessions/{id}/poc/files` answers `generated` (files
 * exist) and, since the package check, `ready` plus `problems` (the files add
 * up to a package worth handing over). The tab used to read only `generated`,
 * so a package the API itself called not ready — an unwired run_poc.py, no gaik
 * in the requirements — was shown as "Generated PoC package" with a download
 * button and an enabled sandbox run.
 *
 * An answer without `ready` (the mock store, an older api) does not say the
 * package is bad, so it counts as ready: only an explicit `ready: false`
 * withholds the download and the run.
 */
export type PocPackageState = {
  generated: boolean;
  ready: boolean;
  problems: string[];
  files: string[];
  /**
   * What the deployable package carries beside the package's own files: the
   * blueprint, the workflow diagrams and the documentation, by their names in
   * it (`solution_files`). Empty from the mock store and an api without it.
   */
  solutionFiles: string[];
  /** The sandbox run wizard_api has recorded as successful, or null (#143, #253). */
  recordedRun: string | null;
  /** Digest of the files a preflight reads; a new one means the agent changed the package. */
  version: string | null;
  /** wizard_api's digest of the package as a test run is tied to it (`package_digest`); null from an api without it. */
  packageDigest: string | null;
  /** That digest as it was for the run recorded as successful (the session's `last_successful_run_package`). */
  testedPackage: string | null;
};

export const NO_POC_PACKAGE: PocPackageState = {
  generated: false,
  ready: false,
  problems: [],
  files: [],
  solutionFiles: [],
  recordedRun: null,
  version: null,
  packageDigest: null,
  testedPackage: null,
};

export function pocPackageState(raw: unknown): PocPackageState {
  if (typeof raw !== "object" || raw === null) return NO_POC_PACKAGE;
  const d = raw as {
    generated?: unknown;
    ready?: unknown;
    problems?: unknown;
    files?: unknown;
    solution_files?: unknown;
    recordedRun?: unknown;
    version?: unknown;
    package_digest?: unknown;
    testedPackage?: unknown;
  };
  const text = (v: unknown): string | null => (typeof v === "string" && v ? v : null);
  const recordedRun = text(d.recordedRun);
  const version = text(d.version);
  const testedPackage = text(d.testedPackage);
  const generated = Boolean(d.generated);
  if (!generated) return { ...NO_POC_PACKAGE, recordedRun, testedPackage };
  const strings = (v: unknown): string[] =>
    Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
  return {
    generated: true,
    ready: d.ready !== false,
    problems: strings(d.problems),
    files: strings(d.files),
    solutionFiles: strings(d.solution_files),
    recordedRun,
    version,
    packageDigest: text(d.package_digest),
    testedPackage,
  };
}

/** The two answers describe the same package, so there is nothing to re-render. */
export function samePocPackage(a: PocPackageState, b: PocPackageState): boolean {
  return (
    a.generated === b.generated &&
    a.ready === b.ready &&
    a.recordedRun === b.recordedRun &&
    a.version === b.version &&
    a.packageDigest === b.packageDigest &&
    a.testedPackage === b.testedPackage &&
    a.problems.length === b.problems.length &&
    a.problems.every((p, i) => p === b.problems[i]) &&
    a.files.length === b.files.length &&
    a.files.every((f, i) => f === b.files[i]) &&
    // The documentation is written after the test run: the list grows without the package changing.
    a.solutionFiles.length === b.solutionFiles.length &&
    a.solutionFiles.every((f, i) => f === b.solutionFiles[i])
  );
}
