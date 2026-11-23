import { describe, expect, it, vi } from "vitest";

const cookiesMock = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("next/headers", () => ({
  cookies: async () => cookiesMock,
}));

import { BPMN_TASK_TYPES } from "@/lib/bpmn-edit-state";
import { DEFAULT_LOCALE, LOCALES, dictionary, getI18n, getLocale } from "@/lib/i18n";

describe("getLocale", () => {
  it("defaults to the default locale when no cookie is set", async () => {
    cookiesMock.get.mockReturnValue(undefined);
    expect(await getLocale()).toBe(DEFAULT_LOCALE);
  });

  it("honours a valid locale cookie", async () => {
    cookiesMock.get.mockReturnValue({ value: "en" });
    expect(await getLocale()).toBe("en");
  });

  it("falls back to the default for an unrecognised cookie value", async () => {
    cookiesMock.get.mockReturnValue({ value: "sv" });
    expect(await getLocale()).toBe(DEFAULT_LOCALE);
  });
});

describe("getI18n", () => {
  it("returns the dict matching the current locale", async () => {
    cookiesMock.get.mockReturnValue({ value: "en" });
    const { locale, t } = await getI18n();
    expect(locale).toBe("en");
    expect(t.appName).toBe("GAIK Solution Wizard");
  });

  it("every locale's dict exposes the exact same key set (no missing translations)", async () => {
    const dicts = await Promise.all(
      LOCALES.map(async (loc) => {
        cookiesMock.get.mockReturnValue({ value: loc });
        return (await getI18n()).t;
      }),
    );
    const [first, ...rest] = dicts.map((d) => Object.keys(d).sort());
    for (const keys of rest) {
      expect(keys).toEqual(first);
    }
  });

  it("every locale's phases array has the same length (13 wizard steps)", async () => {
    for (const loc of LOCALES) {
      cookiesMock.get.mockReturnValue({ value: loc });
      const { t } = await getI18n();
      expect(t.phases).toHaveLength(13);
      expect(t.phases.every((p) => typeof p === "string" && p.length > 0)).toBe(true);
    }
  });

  it("every locale names each element the diagram's properties can show", () => {
    // What the canvas lets the user select for a rename (lib/bpmn-edit-state).
    const types = [...BPMN_TASK_TYPES, "bpmn:ExclusiveGateway", "bpmn:ParallelGateway", "bpmn:DataObjectReference"];
    for (const loc of LOCALES) {
      const names = dictionary(loc).wsBpmnTypeNames;
      for (const type of types) expect(names[type], `${loc} ${type}`).toBeTruthy();
    }
  });

  it("every locale defines all four gate statuses", async () => {
    for (const loc of LOCALES) {
      cookiesMock.get.mockReturnValue({ value: loc });
      const { t } = await getI18n();
      expect(Object.keys(t.gates).sort()).toEqual(["approved", "locked", "pending", "rejected"]);
    }
  });

  it("every locale tells the user, in the chat and on sign-in, that the assistant is an AI", async () => {
    const ai = { fi: /tekoäly/i, en: /\bAI\b/ } as const;
    for (const loc of LOCALES) {
      cookiesMock.get.mockReturnValue({ value: loc });
      const { t } = await getI18n();
      for (const text of [t.chatGreeting, t.chatAiNotice, t.chatAssistantLabel, t.loginAiNotice]) {
        expect(text).toMatch(ai[loc]);
      }
    }
  });

  it("every locale tells a user whose own agents are all busy to wait, in their language", async () => {
    const busy = { fi: /wizard-sessiota/, en: /wizard sessions working/ } as const;
    for (const loc of LOCALES) {
      cookiesMock.get.mockReturnValue({ value: loc });
      const { t } = await getI18n();
      expect(t.chatErrors.agentBusy).toMatch(busy[loc]);
      expect(t.chatErrors.rateLimited.length).toBeGreaterThan(0);
    }
  });
});

describe("the texts of the Blueprint and Plan tabs", () => {
  it("name a step type in business words, the same on both tabs", () => {
    // One key per step type, read by both tabs: the Plan tab had its own set.
    const names = {
      fi: ["Tekoäly", "Ihmisen tarkistus", "Syöte tai tulos"],
      en: ["AI step", "Human review", "Input or output"],
    } as const;
    for (const loc of LOCALES) {
      const t = dictionary(loc);
      expect([t.wsStepAi, t.wsStepHuman, t.wsStepIo]).toEqual(names[loc]);
      expect(Object.keys(t).filter((key) => key.startsWith("planRole"))).toEqual([]);
      for (const name of names[loc]) expect(t.wsFormTypeHint).toContain(name);
    }
  });

  it("carry no ticket id", () => {
    const texts = (value: unknown): string[] =>
      typeof value === "string"
        ? [value]
        : value && typeof value === "object"
          ? Object.values(value).flatMap(texts)
          : [];
    for (const loc of LOCALES) {
      expect(texts(dictionary(loc)).filter((text) => /\b(SME|US)-[A-Z]?\d/.test(text))).toEqual([]);
    }
  });
});
