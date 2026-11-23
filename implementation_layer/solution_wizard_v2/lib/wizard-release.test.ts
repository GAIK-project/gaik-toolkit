import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  alreadyReleased,
  forgetReleased,
  releaseFailed,
  releaseStarted,
  rememberReleased,
} from "./wizard-release";

const SESSION = "2fa204b7";
const KEY = `wizard-released:${SESSION}`;

describe("the mark of a released wizard", () => {
  const store = new Map<string, string>();
  beforeEach(() => {
    store.clear();
    vi.stubGlobal("window", {
      localStorage: {
        getItem: (k: string) => store.get(k) ?? null,
        setItem: (k: string, v: string) => void store.set(k, v),
        removeItem: (k: string) => void store.delete(k),
      },
    });
  });
  afterEach(() => {
    forgetReleased(SESSION);
    vi.unstubAllGlobals();
  });

  it("is kept for the next load of the finished session, per session", async () => {
    expect(alreadyReleased(SESSION)).toBe(false);
    rememberReleased(SESSION);
    expect(alreadyReleased(SESSION)).toBe(true);
    expect(alreadyReleased("another-session")).toBe(false);

    // A full page load leaves only the storage.
    vi.resetModules();
    expect((await import("./wizard-release")).alreadyReleased(SESSION)).toBe(true);
  });

  it("goes when the session is seen not finished, so a second approval releases the wizard again", async () => {
    rememberReleased(SESSION);
    // Gate 4 was reopened: the page shows the session waiting at it.
    forgetReleased(SESSION);
    expect(store.has(KEY)).toBe(false);
    expect(alreadyReleased(SESSION)).toBe(false);
    vi.resetModules();
    expect((await import("./wizard-release")).alreadyReleased(SESSION)).toBe(false);

    // Approved again: released again, and remembered again.
    rememberReleased(SESSION);
    expect(alreadyReleased(SESSION)).toBe(true);
  });

  it("holds a second request back while one is on its way, and lets it through after a failure", () => {
    releaseStarted(SESSION);
    expect(alreadyReleased(SESSION)).toBe(true);
    expect(store.size).toBe(0);
    releaseFailed(SESSION);
    expect(alreadyReleased(SESSION)).toBe(false);
  });

  it("does not remember a release answered after the session was seen not finished again", () => {
    // The release was asked for, then Gate 4 was reopened before the answer came.
    const started = releaseStarted(SESSION);
    forgetReleased(SESSION);
    rememberReleased(SESSION, started);
    expect(alreadyReleased(SESSION)).toBe(false);
    expect(store.size).toBe(0);

    // The release of the finish that stands is remembered.
    rememberReleased(SESSION, releaseStarted(SESSION));
    expect(store.get(KEY)).toBe("1");
  });

  it("works for the page load in a browser that blocks storage", () => {
    vi.stubGlobal("window", {
      get localStorage(): Storage {
        throw new Error("blocked");
      },
    });
    rememberReleased(SESSION);
    expect(alreadyReleased(SESSION)).toBe(true);
    forgetReleased(SESSION);
    expect(alreadyReleased(SESSION)).toBe(false);
  });
});
