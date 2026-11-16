import { describe, expect, it } from "vitest";
import { STARTING_AFTER_MS, startingLineDelay } from "./wizard-start";

describe("startingLineDelay", () => {
  it("says at once that the wizard is starting when none is held for the session", () => {
    expect(startingLineDelay(false)).toBe(0);
  });

  it("waits for a late answer when a wizard is held", () => {
    expect(startingLineDelay(true)).toBe(STARTING_AFTER_MS);
  });

  it("waits for a late answer when the page does not know", () => {
    expect(startingLineDelay(undefined)).toBe(STARTING_AFTER_MS);
    expect(startingLineDelay(null)).toBe(STARTING_AFTER_MS);
  });
});
