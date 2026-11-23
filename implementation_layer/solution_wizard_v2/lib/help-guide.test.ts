import { describe, expect, it } from "vitest";
import { helpGuide } from "@/lib/help-guide";
import { isPublicPage } from "@/lib/public-pages";
import { dictionary } from "@/lib/i18n";

describe("help guide", () => {
  it("has the same sections in both languages", () => {
    const shape = (locale: "fi" | "en") =>
      helpGuide(locale).sections.map((s) => [Boolean(s.text), s.items?.length ?? 0]);
    expect(shape("fi")).toEqual(shape("en"));
  });

  it("names the buttons and tabs as the app labels them", () => {
    for (const locale of ["fi", "en"] as const) {
      const t = dictionary(locale);
      const text = JSON.stringify(helpGuide(locale));
      for (const label of [
        t.newSession,
        t.gateApproveShort,
        t.gateRequestChanges,
        t.wsTabFlow,
        t.wsTabPoc,
        t.planSchema.title,
      ]) {
        expect(text).toContain(label);
      }
    }
  });

  it("tells how long a session is kept", () => {
    expect(JSON.stringify(helpGuide("fi"))).toContain("90 päivään");
    expect(JSON.stringify(helpGuide("en"))).toContain("90 days");
  });

  it("is read after signing in", () => {
    expect(isPublicPage("/help")).toBe(false);
  });
});
