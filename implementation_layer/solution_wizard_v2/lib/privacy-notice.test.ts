import { describe, expect, it } from "vitest";
import { config } from "@/proxy";
import { privacyNotice } from "@/lib/privacy-notice";
import { isPublicPage } from "@/lib/public-pages";

const COMPLETE = {
  WIZARD_PRIVACY_CONTROLLER: "Example Oy",
  WIZARD_PRIVACY_CONTACT: "privacy@example.com",
  WIZARD_PRIVACY_LEGAL_BASIS: "Legitimate interest",
};
const text = (locale: "fi" | "en", env = {}) => JSON.stringify(privacyNotice(locale, env));

describe("privacy notice", () => {
  it("is a draft until the deployment names the controller, contact and legal basis", () => {
    for (const locale of ["fi", "en"] as const) {
      expect(privacyNotice(locale, {}).draftNote).not.toBeNull();
      expect(
        privacyNotice(locale, { ...COMPLETE, WIZARD_PRIVACY_CONTACT: " " }).draftNote,
      ).not.toBeNull();
      expect(privacyNotice(locale, COMPLETE).draftNote).toBeNull();
    }
  });

  it("shows what the deployment set", () => {
    for (const value of Object.values(COMPLETE)) {
      expect(text("fi", COMPLETE)).toContain(value);
      expect(text("en", COMPLETE)).toContain(value);
    }
  });

  it("has the same sections in both languages", () => {
    const shape = (locale: "fi" | "en") =>
      privacyNotice(locale, {}).sections.map((s) => [Boolean(s.text), s.items?.length ?? 0]);
    expect(shape("fi")).toEqual(shape("en"));
  });
});

describe("who can read it", () => {
  it("is open without signing in, and nothing below it is", () => {
    expect(isPublicPage("/privacy")).toBe(true);
    expect(isPublicPage("/login")).toBe(true);
    expect(isPublicPage("/privacy/other")).toBe(false);
    expect(isPublicPage("/privacy-policy")).toBe(false);
    expect(isPublicPage("/")).toBe(false);
    expect(isPublicPage("/sessions/abc")).toBe(false);
  });

  it("still goes through the proxy", () => {
    expect(config.matcher.some((m) => new RegExp(`^${m}$`).test("/privacy"))).toBe(true);
  });
});
