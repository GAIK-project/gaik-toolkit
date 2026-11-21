import { describe, expect, it } from "vitest";
import { startText } from "@/lib/start-text";

describe("startText", () => {
  it("sends what the state holds", () => {
    expect(startText("  Laskujen kentät  ", "anything")).toBe("Laskujen kentät");
  });

  it("falls back to the field when the state never got the words", () => {
    expect(startText("", "Typed before the page loaded")).toBe("Typed before the page loaded");
    expect(startText("   ", "  Pasted early  ")).toBe("Pasted early");
  });

  it("sends nothing when both are empty", () => {
    expect(startText("", "")).toBe("");
    expect(startText("", null)).toBe("");
    expect(startText(" ", undefined)).toBe("");
  });
});
