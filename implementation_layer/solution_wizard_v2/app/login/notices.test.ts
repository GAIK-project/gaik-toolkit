import { describe, expect, it, vi } from "vitest";

const cookiesMock = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("next/headers", () => ({
  cookies: async () => cookiesMock,
}));

import { LOCALES, getI18n } from "@/lib/i18n";
import { loginError, loginMessage } from "./notices";

describe("login notices", () => {
  it("shows a known code in the current locale", async () => {
    cookiesMock.get.mockReturnValue({ value: "en" });
    const { t } = await getI18n();
    expect(loginError(t, "credentials")).toBe("Wrong email or password.");
    expect(loginMessage(t, "signed-up")).toMatch(/^Signed up/);
  });

  it("shows nothing for text that is not a known code", async () => {
    cookiesMock.get.mockReturnValue({ value: "fi" });
    const { t } = await getI18n();
    expect(loginError(t, "Your account is locked, call +358 00 000")).toBeNull();
    expect(loginMessage(t, "<b>hello</b>")).toBeNull();
    expect(loginError(t, undefined)).toBeNull();
    expect(loginError(t, "toString")).toBeNull();
  });

  it("has every code translated in every locale", async () => {
    for (const loc of LOCALES) {
      cookiesMock.get.mockReturnValue({ value: loc });
      const { t } = await getI18n();
      for (const text of [...Object.values(t.loginErrors), ...Object.values(t.loginMessages)]) {
        expect(text.length).toBeGreaterThan(0);
      }
    }
  });
});
