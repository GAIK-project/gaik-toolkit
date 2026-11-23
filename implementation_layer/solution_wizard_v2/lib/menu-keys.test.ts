import { describe, expect, it } from "vitest";
import { nextMenuIndex } from "./menu-keys";

describe("nextMenuIndex", () => {
  it("steps down and up through the items", () => {
    expect(nextMenuIndex("ArrowDown", 0, 4)).toBe(1);
    expect(nextMenuIndex("ArrowDown", 2, 4)).toBe(3);
    expect(nextMenuIndex("ArrowUp", 3, 4)).toBe(2);
    expect(nextMenuIndex("ArrowUp", 1, 4)).toBe(0);
  });

  it("wraps around at both ends", () => {
    expect(nextMenuIndex("ArrowDown", 3, 4)).toBe(0);
    expect(nextMenuIndex("ArrowUp", 0, 4)).toBe(3);
  });

  it("starts from the first item going down and the last going up when none has the focus", () => {
    expect(nextMenuIndex("ArrowDown", -1, 4)).toBe(0);
    expect(nextMenuIndex("ArrowUp", -1, 4)).toBe(3);
  });

  it("goes to the ends with Home and End", () => {
    expect(nextMenuIndex("Home", 2, 4)).toBe(0);
    expect(nextMenuIndex("End", 1, 4)).toBe(3);
  });

  it("leaves every other key, and a menu without items, alone", () => {
    for (const key of ["Tab", "Enter", " ", "Escape", "ArrowLeft", "ArrowRight", "a"]) {
      expect(nextMenuIndex(key, 1, 4)).toBeNull();
    }
    expect(nextMenuIndex("ArrowDown", -1, 0)).toBeNull();
    expect(nextMenuIndex("Home", 0, 0)).toBeNull();
  });
});
