import { describe, expect, it } from "vitest";
import { NO_POC_PACKAGE, pocPackageState, samePocPackage } from "./poc-package-state";

describe("pocPackageState", () => {
  it("is not generated for nothing, garbage and generated:false", () => {
    expect(pocPackageState(null)).toEqual(NO_POC_PACKAGE);
    expect(pocPackageState("x")).toEqual(NO_POC_PACKAGE);
    expect(pocPackageState({ generated: false, files: ["a"] })).toEqual(NO_POC_PACKAGE);
  });

  it("a package the api calls ready is ready", () => {
    const s = pocPackageState({ generated: true, ready: true, files: ["run_poc.py"], problems: [] });
    expect(s).toEqual({
      generated: true,
      ready: true,
      problems: [],
      files: ["run_poc.py"],
      solutionFiles: [],
      recordedRun: null,
      version: null,
      packageDigest: null,
      testedPackage: null,
    });
  });

  it("carries the api's digests: of the package as it is, and of the package the successful run tested", () => {
    const s = pocPackageState({
      generated: true,
      files: ["run_poc.py"],
      version: "v7",
      package_digest: "d2",
      testedPackage: "d1",
    });
    expect(s.packageDigest).toBe("d2");
    expect(s.testedPackage).toBe("d1");
    // An api that keeps none, and values that are not digests.
    expect(pocPackageState({ generated: true, files: [] }).packageDigest).toBeNull();
  });

  it("reads what the deployable package carries beside the package's files, and notices when it grows", () => {
    const before = pocPackageState({ generated: true, files: ["run_poc.py"] });
    expect(before.solutionFiles).toEqual([]);
    const after = pocPackageState({
      generated: true,
      files: ["run_poc.py"],
      solution_files: ["use_case.blueprint.json", "workflow.bpmn", 7, "docs/user_guide.md"],
    });
    expect(after.solutionFiles).toEqual(["use_case.blueprint.json", "workflow.bpmn", "docs/user_guide.md"]);
    // The documentation arrives after the test run, with the package itself unchanged.
    expect(samePocPackage(before, after)).toBe(false);
    expect(samePocPackage(after, pocPackageState({ ...after, solution_files: after.solutionFiles }))).toBe(true);
    expect(pocPackageState({ generated: true, files: [], package_digest: 5, testedPackage: "" })).toMatchObject({
      packageDigest: null,
      testedPackage: null,
    });
    // The run's digest is the session's: it is there without a package too.
    expect(pocPackageState({ generated: false, testedPackage: "d1" }).testedPackage).toBe("d1");
  });

  it("two answers that differ in a digest are not the same package state", () => {
    const a = pocPackageState({ generated: true, files: [], package_digest: "d1", testedPackage: "d1" });
    expect(samePocPackage(a, { ...a })).toBe(true);
    expect(samePocPackage(a, { ...a, packageDigest: "d2" })).toBe(false);
    expect(samePocPackage(a, { ...a, testedPackage: "d2" })).toBe(false);
  });

  it("an explicit ready:false is not ready and keeps the api's reasons", () => {
    const s = pocPackageState({
      generated: true,
      ready: false,
      files: ["README.md"],
      problems: ["run_poc.py is missing"],
    });
    expect(s.generated).toBe(true);
    expect(s.ready).toBe(false);
    expect(s.problems).toEqual(["run_poc.py is missing"]);
  });

  it("carries the package version when the api gives one", () => {
    expect(pocPackageState({ generated: true, ready: true, version: "ab12" }).version).toBe("ab12");
    expect(pocPackageState({ generated: true, ready: true, version: "" }).version).toBeNull();
    expect(pocPackageState({ generated: true, ready: true }).version).toBeNull();
  });

  it("an answer without ready (mock store, older api) does not withhold the package", () => {
    expect(pocPackageState({ generated: true, files: ["a"] }).ready).toBe(true);
  });

  it("ignores non-string entries in files and problems", () => {
    const s = pocPackageState({ generated: true, ready: false, files: ["a", 1, null], problems: [2, "p"] });
    expect(s.files).toEqual(["a"]);
    expect(s.problems).toEqual(["p"]);
  });

  it("carries the run the api has recorded, and only a real one (#253)", () => {
    expect(pocPackageState({ generated: true, files: [], recordedRun: "20261004-abc" }).recordedRun).toBe(
      "20261004-abc",
    );
    expect(pocPackageState({ generated: true, files: [], recordedRun: "" }).recordedRun).toBeNull();
    expect(pocPackageState({ generated: true, files: [], recordedRun: 42 }).recordedRun).toBeNull();
    expect(pocPackageState({ generated: true, files: [] }).recordedRun).toBeNull();
    // A recorded run survives a package that is (temporarily) not generated.
    expect(pocPackageState({ generated: false, recordedRun: "r1" }).recordedRun).toBe("r1");
  });
});

describe("samePocPackage", () => {
  const ready = pocPackageState({
    generated: true,
    ready: true,
    files: ["run_poc.py", "config.yaml"],
    problems: [],
    version: "v1",
  });

  it("is true for two answers with the same content", () => {
    expect(samePocPackage(ready, pocPackageState(JSON.parse(JSON.stringify({ ...ready }))))).toBe(true);
    expect(samePocPackage(NO_POC_PACKAGE, { ...NO_POC_PACKAGE })).toBe(true);
  });

  it("is false when the agent rewrote the package (version), or anything else moved", () => {
    expect(samePocPackage(ready, { ...ready, version: "v2" })).toBe(false);
    expect(samePocPackage(ready, { ...ready, ready: false, problems: ["TODO"] })).toBe(false);
    expect(samePocPackage(ready, { ...ready, files: ["run_poc.py"] })).toBe(false);
    expect(samePocPackage(ready, { ...ready, recordedRun: "r1" })).toBe(false);
  });
});
