import { describe, expect, it } from "vitest";
import {
  packageStatus,
  parseStoredPreflight,
  preflightIsFinding,
  preflightOutcome,
  preflightProblems,
  preflightStorageKey,
  readStoredPreflight,
  shouldStartPreflight,
  unfinishedPreflight,
  writeStoredPreflight,
  type PreflightStore,
} from "./poc-preflight";

describe("packageStatus", () => {
  const base = { loaded: true, generated: true, complete: true } as const;

  it("is ready to run only once the preflight passed", () => {
    expect(packageStatus({ ...base, preflight: "ok" })).toBe("ready");
    expect(packageStatus({ ...base, preflight: "failed" })).toBe("failed");
    expect(packageStatus({ ...base, preflight: "running" })).toBe("checking");
  });

  it("keeps a check that could not finish apart from a failed one", () => {
    expect(packageStatus({ ...base, preflight: "unfinished" })).toBe("unfinished");
  });

  it("calls complete files that nobody checked a generated package, not ready", () => {
    expect(packageStatus({ ...base, preflight: "idle" })).toBe("unchecked");
  });

  it("reports loading, a missing package and missing files before any check", () => {
    expect(packageStatus({ ...base, loaded: false, preflight: "ok" })).toBe("loading");
    expect(packageStatus({ ...base, generated: false, preflight: "idle" })).toBe("missing");
    expect(packageStatus({ ...base, complete: false, preflight: "ok" })).toBe("incomplete");
  });
});

describe("shouldStartPreflight", () => {
  const base = { onPocTab: true, ready: true, version: "v1", checkedVersion: null };

  it("starts for a ready package nobody has checked", () => {
    expect(shouldStartPreflight(base)).toBe(true);
  });

  it("does not start off the PoC tab, for a package that is not ready, or without a version", () => {
    expect(shouldStartPreflight({ ...base, onPocTab: false })).toBe(false);
    expect(shouldStartPreflight({ ...base, ready: false })).toBe(false);
    expect(shouldStartPreflight({ ...base, version: null })).toBe(false);
  });

  it("does not start twice for the same version, but does for a rewritten package", () => {
    expect(shouldStartPreflight({ ...base, checkedVersion: "v1" })).toBe(false);
    expect(shouldStartPreflight({ ...base, version: "v2", checkedVersion: "v1" })).toBe(true);
  });
});

describe("preflightProblems", () => {
  it("keeps only the PROBLEM lines, without the prefix", () => {
    expect(
      preflightProblems([
        "Loading",
        "PROBLEM: run_poc.py line 3: import pandas failed (ModuleNotFoundError: No module named 'pandas')",
        "=== PREFLIGHT FAILED: 1 problem(s) ===",
      ]),
    ).toEqual(["run_poc.py line 3: import pandas failed (ModuleNotFoundError: No module named 'pandas')"]);
  });
});

describe("preflightOutcome", () => {
  it("a succeeded Job with no problems is ok", () => {
    expect(preflightOutcome("succeeded", ["=== PREFLIGHT OK ==="])).toEqual({ phase: "ok", problems: [] });
  });

  it("a failed Job lists the problems from the log", () => {
    const out = preflightOutcome("failed", ["PROBLEM: schema cannot be loaded (ValidationError: x)"]);
    expect(out.phase).toBe("failed");
    expect(out.problems).toEqual(["schema cannot be loaded (ValidationError: x)"]);
  });

  it("a Job that ended without a finding did not finish, with the Job's own message as the reason", () => {
    expect(preflightOutcome("timeout", [], "the run passed its limit")).toEqual({
      phase: "unfinished",
      problems: [],
      reason: "the run passed its limit",
    });
    expect(preflightOutcome("failed", [])).toEqual({ phase: "unfinished", problems: [], reason: null });
    expect(preflightOutcome("failed", ["Traceback (most recent call last):"], "sandbox error").phase).toBe(
      "unfinished",
    );
  });

  it("findings printed before the time limit are still findings", () => {
    expect(preflightOutcome("timeout", ["PROBLEM: x"], "the run passed its limit")).toEqual({
      phase: "failed",
      problems: ["x"],
    });
  });

  it("a succeeded Job that still printed a problem is not ok", () => {
    expect(preflightOutcome("succeeded", ["PROBLEM: x"]).phase).toBe("failed");
  });
});

describe("preflightIsFinding", () => {
  it("a pass and a failure the log explains are findings about the package", () => {
    expect(preflightIsFinding("succeeded", ["=== PREFLIGHT OK ==="])).toBe(true);
    expect(preflightIsFinding("failed", ["PROBLEM: schema cannot be loaded"])).toBe(true);
    expect(preflightIsFinding("succeeded", ["PROBLEM: x"])).toBe(true);
  });

  it("a Job that failed without naming a problem says nothing about the package", () => {
    expect(preflightIsFinding("timeout", [])).toBe(false);
    expect(preflightIsFinding("failed", ["Traceback (most recent call last):"])).toBe(false);
    expect(preflightIsFinding("error", [])).toBe(false);
  });
});

describe("stored preflight", () => {
  function memoryStore(): PreflightStore & { data: Map<string, string> } {
    const data = new Map<string, string>();
    return {
      data,
      getItem: (k) => data.get(k) ?? null,
      setItem: (k, v) => void data.set(k, v),
      removeItem: (k) => void data.delete(k),
    };
  }
  const throwing: PreflightStore = {
    getItem: () => {
      throw new Error("SecurityError");
    },
    setItem: () => {
      throw new Error("QuotaExceededError");
    },
    removeItem: () => {
      throw new Error("SecurityError");
    },
  };

  it("keeps a finished check per session and reads it back", () => {
    const store = memoryStore();
    writeStoredPreflight(store, "s1", { version: "v1", runId: "pre_1", phase: "failed", problems: ["no module x"] });
    expect(readStoredPreflight(store, "s1")).toEqual({
      version: "v1",
      runId: "pre_1",
      phase: "failed",
      problems: ["no module x"],
    });
    expect(readStoredPreflight(store, "s2")).toBeNull();
    expect([...store.data.keys()]).toEqual([preflightStorageKey("s1")]);
  });

  it("forgets the entry when asked", () => {
    const store = memoryStore();
    writeStoredPreflight(store, "s1", { version: "v1", runId: null, phase: "ok", problems: [] });
    writeStoredPreflight(store, "s1", null);
    expect(readStoredPreflight(store, "s1")).toBeNull();
  });

  it("survives storage that is missing or throws", () => {
    expect(readStoredPreflight(null, "s1")).toBeNull();
    expect(readStoredPreflight(throwing, "s1")).toBeNull();
    expect(() => writeStoredPreflight(throwing, "s1", { version: "v1", runId: null, phase: "ok", problems: [] })).not.toThrow();
    expect(() => writeStoredPreflight(null, "s1", null)).not.toThrow();
  });

  it("drops garbage and shapes it does not know", () => {
    expect(parseStoredPreflight(null)).toBeNull();
    expect(parseStoredPreflight("{not json")).toBeNull();
    expect(parseStoredPreflight("42")).toBeNull();
    expect(parseStoredPreflight(JSON.stringify({ version: "", phase: "ok" }))).toBeNull();
    expect(parseStoredPreflight(JSON.stringify({ version: "v1", phase: "idle" }))).toBeNull();
    // A check in progress is only worth remembering with the run to follow.
    expect(parseStoredPreflight(JSON.stringify({ version: "v1", phase: "running" }))).toBeNull();
    expect(parseStoredPreflight(JSON.stringify({ version: "v1", phase: "ok", problems: ["a", 3] }))).toEqual({
      version: "v1",
      runId: null,
      phase: "ok",
      problems: ["a"],
    });
  });
});

describe("unfinishedPreflight", () => {
  it("carries no findings, and a reason only when there is one", () => {
    expect(unfinishedPreflight()).toEqual({ phase: "unfinished", problems: [], reason: null });
    expect(unfinishedPreflight("")).toEqual({ phase: "unfinished", problems: [], reason: null });
  });
});
