import { afterEach, describe, expect, test } from "bun:test";
import { isModelStaff } from "./model-tier";

describe("isModelStaff", () => {
  afterEach(() => {
    delete process.env.DEMO_USER_NAME;
  });

  test("haaga-helia.fi addresses are on the team, students and others are not", () => {
    expect(isModelStaff("maija.meikalainen@haaga-helia.fi", undefined)).toBe(
      true,
    );
    expect(isModelStaff("opiskelija@myy.haaga-helia.fi", undefined)).toBe(
      false,
    );
    expect(isModelStaff("someone@haaga-helia.fi.example.com", undefined)).toBe(
      false,
    );
    expect(isModelStaff("someone@example.com", undefined)).toBe(false);
    expect(isModelStaff(null, undefined)).toBe(false);
  });

  test("the shared demo account is on the team", () => {
    process.env.DEMO_USER_NAME = "Demo@Example.com";
    expect(isModelStaff("demo@example.com", undefined)).toBe(true);
  });

  test("an unsigned admin cookie does not count", () => {
    expect(isModelStaff(null, "authenticated")).toBe(false);
  });
});
