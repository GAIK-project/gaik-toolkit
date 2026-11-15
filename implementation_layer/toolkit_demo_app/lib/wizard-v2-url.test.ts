import { describe, expect, test } from "bun:test";
import { wizardV2Url } from "./wizard-v2-url";

describe("wizardV2Url", () => {
  test("an https address is used as the link", () => {
    expect(wizardV2Url(" https://wizard.example.org ")).toBe(
      "https://wizard.example.org/",
    );
  });

  test("an unset or empty value gives no link", () => {
    expect(wizardV2Url(undefined)).toBeNull();
    expect(wizardV2Url("  ")).toBeNull();
  });

  test("a value that is not an http(s) URL gives no link", () => {
    expect(wizardV2Url("wizard.example.org")).toBeNull();
    expect(wizardV2Url("ftp://wizard.example.org")).toBeNull();
  });
});
