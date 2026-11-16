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
   * The deployment package as its zip names its files: `poc/...`, and beside
   * it the blueprint, the diagrams, the documentation and the AI marker. From
   * an answer without `package_files` (the mock store, an older api): the
   * files under `poc/` and what `solution_files` names beside it.
   */
  packageFiles: string[];
  /**
   * What only the working version carries (the test input, a run's output):
   * each by its outermost folder the package has nothing of (`sample_input/`),
   * or by its own path inside a folder the package carries. Empty where the answer
   * does not list the deployment package.
   */
  workOnly: string[];
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
  packageFiles: [],
  workOnly: [],
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
    package_files?: unknown;
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
  const files = strings(d.files);
  const listed = Array.isArray(d.package_files);
  const packageFiles = listed
    ? strings(d.package_files)
    : [...files.map((f) => `poc/${f}`), ...strings(d.solution_files)];
  const inPackage = new Set(packageFiles);
  // The folders the package carries something of, so a file left out of one
  // (src/__pycache__/a.pyc beside src/a.py) is named by itself, not by src/.
  const packageFolders = new Set(
    packageFiles.flatMap((f) => f.split("/").slice(0, -1).map((_, i, parts) => parts.slice(0, i + 1).join("/"))),
  );
  // A left-out file is named by its outermost folder the package has nothing of.
  const workOnlyName = (f: string) => {
    const parts = f.split("/");
    for (let i = 1; i < parts.length; i++) {
      const folder = parts.slice(0, i).join("/");
      if (!packageFolders.has(`poc/${folder}`)) return `${folder}/`;
    }
    return f;
  };
  const workOnly = listed
    ? [...new Set(files.filter((f) => !inPackage.has(`poc/${f}`)).map(workOnlyName))]
    : [];
  return {
    generated: true,
    ready: d.ready !== false,
    problems: strings(d.problems),
    files,
    packageFiles,
    workOnly,
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
    a.packageFiles.length === b.packageFiles.length &&
    a.packageFiles.every((f, i) => f === b.packageFiles[i])
  );
}
