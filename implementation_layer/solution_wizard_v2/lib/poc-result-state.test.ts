import { describe, expect, it, vi } from "vitest";

import {
  gate3Waits,
  handoverState,
  packageChangedSinceRun,
  packageReadFor,
  publishResultStale,
  publishRunWarnings,
  resultIsStale,
  resultStaleFor,
  runWarnings,
  runWarningsFor,
  subscribeResultStale,
} from "@/lib/poc-result-state";

const settled = { wizardReplying: false, packageStale: false, packageVersion: "v2", resultVersion: "v2" };

describe("resultIsStale", () => {
  it("is not, for a result of the package that is there", () => {
    expect(resultIsStale(settled)).toBe(false);
  });

  it("is, while the wizard is replying or the package has not been read since its reply", () => {
    expect(resultIsStale({ ...settled, wizardReplying: true })).toBe(true);
    expect(resultIsStale({ ...settled, packageStale: true })).toBe(true);
  });

  it("is, when the package has changed since the run, until a run of the new one succeeds", () => {
    expect(resultIsStale({ ...settled, resultVersion: "v1" })).toBe(true);
    // The new package's run succeeded: the result is its own again.
    expect(resultIsStale({ ...settled, packageVersion: "v3", resultVersion: "v3" })).toBe(false);
  });

  it("does not hold an unknown version against the result", () => {
    expect(resultIsStale({ ...settled, packageVersion: null })).toBe(false);
    expect(resultIsStale({ ...settled, resultVersion: null })).toBe(false);
    expect(resultIsStale({ ...settled, packageVersion: null, resultVersion: null })).toBe(false);
  });
});

describe("the api's digests", () => {
  it("say the package changed when the run that passed tested another one", () => {
    expect(packageChangedSinceRun("d2", "d1")).toBe(true);
    expect(packageChangedSinceRun("d1", "d1")).toBe(false);
  });

  it("hold nothing against a result when either is missing", () => {
    // An api that keeps no digest, a run recorded before it did, no package.
    expect(packageChangedSinceRun(null, "d1")).toBe(false);
    expect(packageChangedSinceRun("d2", null)).toBe(false);
    expect(packageChangedSinceRun(undefined, undefined)).toBe(false);
    expect(packageChangedSinceRun("", "d1")).toBe(false);
  });

  it("make the result stale after a reload, when the page saw neither the run nor the change", () => {
    // The page has adopted the run as this package's: its own versions agree.
    expect(resultIsStale({ ...settled, packageDigest: "d2", testedDigest: "d1" })).toBe(true);
    expect(resultIsStale({ ...settled, packageDigest: "d2", testedDigest: "d2" })).toBe(false);
    expect(resultIsStale({ ...settled, packageDigest: "d2", testedDigest: null })).toBe(false);
  });
});

describe("gate3Waits", () => {
  const quiet = { stale: false, packageRead: false };

  it("waits on the page's reading until the PoC tab has read the digests itself", () => {
    // Another tab is open, or the PoC tab's answer is on its way.
    expect(gate3Waits(quiet, true)).toBe(true);
    expect(gate3Waits(quiet, false)).toBe(false);
  });

  it("goes by the PoC tab once it has them: a run that passed since the page was read opens the gate", () => {
    expect(gate3Waits({ stale: false, packageRead: true }, true)).toBe(false);
  });

  it("waits whenever the PoC tab says the result is stale", () => {
    expect(gate3Waits({ stale: true, packageRead: true }, false)).toBe(true);
    expect(gate3Waits({ stale: true, packageRead: false }, false)).toBe(true);
  });
});

describe("runWarnings", () => {
  it("reads the messages of an answer that has them", () => {
    expect(
      runWarnings({
        run_id: "r1",
        warnings: [
          { code: "empty_fields", message: " Three fields came back empty. " },
          { code: "low_confidence", message: "One value has low confidence." },
        ],
      }),
    ).toEqual([
      { code: "empty_fields", message: "Three fields came back empty.", records: [] },
      { code: "low_confidence", message: "One value has low confidence.", records: [] },
    ]);
  });

  it("reads the warnings as wizard_api sends them: the records, and the field of a warning about one", () => {
    expect(
      runWarnings({
        run_id: "r1",
        warnings: [
          { code: "empty_record", message: "Record 2 has no values: every field is empty.", records: [2] },
          {
            code: "required_field_empty",
            message: "The required field total is empty in records 1 and 3 and filled in others.",
            records: [1, 3],
            field: "total",
          },
        ],
        record: [],
      }),
    ).toEqual([
      { code: "empty_record", message: "Record 2 has no values: every field is empty.", records: [2] },
      {
        code: "required_field_empty",
        message: "The required field total is empty in records 1 and 3 and filled in others.",
        records: [1, 3],
        field: "total",
      },
    ]);
    // Record numbers that are not numbers are dropped, the warning stays.
    expect(runWarnings({ warnings: [{ code: "x", message: "Look.", records: ["2", 3, 1.5], field: 4 }] })).toEqual([
      { code: "x", message: "Look.", records: [3] },
    ]);
  });

  it("has none for an answer without the field, an empty list or anything else", () => {
    expect(runWarnings({ run_id: "r1" })).toEqual([]);
    expect(runWarnings({ warnings: [] })).toEqual([]);
    expect(runWarnings({ warnings: "many" })).toEqual([]);
    expect(runWarnings(null)).toEqual([]);
    expect(runWarnings("x")).toEqual([]);
  });

  it("drops an entry with no message and keeps one with no code", () => {
    expect(runWarnings({ warnings: [{ code: "x" }, { message: "  " }, null, { message: "Check the dates." }] })).toEqual([
      { code: "", message: "Check the dates.", records: [] },
    ]);
  });
});

describe("handoverState", () => {
  const recorded = { packageReady: true, runRecorded: true, shownRunHasWarnings: false };

  it("is ready after a recorded run with nothing to check", () => {
    expect(handoverState(recorded)).toBe("ready");
  });

  it("asks to check the result when the run in view finished with warnings", () => {
    expect(handoverState({ ...recorded, shownRunHasWarnings: true })).toBe("check");
  });

  it("stays locked until a run is recorded, whatever the run in view said", () => {
    expect(handoverState({ ...recorded, runRecorded: false })).toBe("locked");
    expect(handoverState({ ...recorded, runRecorded: false, shownRunHasWarnings: true })).toBe("locked");
  });

  it("has nothing to hand over without a package", () => {
    expect(handoverState({ packageReady: false, runRecorded: true, shownRunHasWarnings: true })).toBe("no_package");
  });
});

describe("the run's warnings between the workspace and the finished solution's banner", () => {
  // The workspace sends the false as it unmounts (workspace-panel); this pins
  // what the store does with it, not that the workspace sends it.
  it("are kept per session, told once per change and cleared by a false", () => {
    const listener = vi.fn();
    const stop = subscribeResultStale(listener);
    expect(runWarningsFor("s1")).toBe(false);

    publishRunWarnings("s1", true);
    publishRunWarnings("s1", true);
    expect(runWarningsFor("s1")).toBe(true);
    expect(runWarningsFor("s2")).toBe(false);
    // The stale word is another matter.
    expect(resultStaleFor("s1")).toBe(false);
    expect(listener).toHaveBeenCalledTimes(1);

    publishRunWarnings("s1", false);
    expect(runWarningsFor("s1")).toBe(false);
    expect(listener).toHaveBeenCalledTimes(2);
    stop();
  });
});

describe("the stale word between the PoC tab and the approve buttons", () => {
  it("is kept per session and told to whoever listens, once per change", () => {
    const listener = vi.fn();
    const stop = subscribeResultStale(listener);
    expect(resultStaleFor("s1")).toBe(false);

    publishResultStale("s1", true);
    publishResultStale("s1", true);
    expect(resultStaleFor("s1")).toBe(true);
    expect(resultStaleFor("s2")).toBe(false);
    expect(listener).toHaveBeenCalledTimes(1);

    publishResultStale("s1", false);
    expect(resultStaleFor("s1")).toBe(false);
    expect(listener).toHaveBeenCalledTimes(2);

    stop();
    publishResultStale("s1", true);
    expect(listener).toHaveBeenCalledTimes(2);
    publishResultStale("s1", false);
  });

  it("says whether the tab holds the api's digests, and tells of that change too", () => {
    const listener = vi.fn();
    const stop = subscribeResultStale(listener);
    expect(packageReadFor("s1")).toBe(false);

    publishResultStale("s1", false, true);
    expect(packageReadFor("s1")).toBe(true);
    expect(resultStaleFor("s1")).toBe(false);
    expect(listener).toHaveBeenCalledTimes(1);
    publishResultStale("s1", false, true);
    expect(listener).toHaveBeenCalledTimes(1);

    // The tab goes away: its word goes with it.
    publishResultStale("s1", false);
    expect(packageReadFor("s1")).toBe(false);
    expect(listener).toHaveBeenCalledTimes(2);
    stop();
  });
});
