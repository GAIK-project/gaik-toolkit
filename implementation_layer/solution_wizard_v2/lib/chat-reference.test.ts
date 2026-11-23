import { describe, expect, it, vi } from "vitest";

vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => undefined }) }));

import { LOCALES, dictionary } from "./i18n";
import { fillTemplate, quoteOneLine } from "./chat-template";
import {
  GATE_APPROVED_WAKE_TEMPLATES,
  approvedGateIn,
  asChatReference,
  referenceMessage,
} from "./chat-reference";

describe("referenceMessage", () => {
  it("starts with the reference's line, then a blank line, then what the user wrote", () => {
    expect(referenceMessage('Koskee vaihetta 3, lainattuna: "Luokittelu"', "Lisää tarkistus.")).toBe(
      'Koskee vaihetta 3, lainattuna: "Luokittelu"\n\nLisää tarkistus.',
    );
  });

  it("keeps the user's own line breaks and trims the ends", () => {
    expect(referenceMessage("Kohta 1", "  eka\ntoka  \n")).toBe("Kohta 1\n\neka\ntoka");
  });

  it("is empty when the user wrote nothing, so a chip alone sends nothing", () => {
    expect(referenceMessage("Kohta 1", "")).toBe("");
    expect(referenceMessage("Kohta 1", "  \n ")).toBe("");
  });

  it("keeps the reference on one line", () => {
    expect(referenceMessage("Kohta 1\nlainattuna", "vastaus")).toBe("Kohta 1 lainattuna\n\nvastaus");
  });

  it("builds the checklist answer the way the inline answer did, quote as data", () => {
    const t = dictionary("fi");
    const prefix = fillTemplate(t.gatheringAskPrefix, {
      n: "2",
      question: quoteOneLine('Who will "use"\nthe system?'),
    });
    expect(referenceMessage(prefix, "Asiakaspalvelu")).toBe(
      "Vastaus tarkistuslistan kohtaan 2, lainattuna: \"Who will 'use' the system?\"\n\nAsiakaspalvelu",
    );
  });
});

describe("asChatReference", () => {
  it("takes the fields of a reference", () => {
    expect(asChatReference({ key: "step:a", label: " Vaihe 1 ", prefix: "Koskee vaihetta 1", draft: "Muuta " })).toEqual({
      key: "step:a",
      label: "Vaihe 1",
      prefix: "Koskee vaihetta 1",
      draft: "Muuta ",
    });
    expect(asChatReference({ key: "k", label: "L", prefix: "P" })).toEqual({ key: "k", label: "L", prefix: "P" });
  });

  it("refuses anything that is not a reference", () => {
    expect(asChatReference(null)).toBeNull();
    expect(asChatReference("text")).toBeNull();
    expect(asChatReference({ key: "k", label: "L" })).toBeNull();
    expect(asChatReference({ key: "k", label: "", prefix: "P" })).toBeNull();
    expect(asChatReference({ key: "k", label: "L", prefix: " \n " })).toBeNull();
    expect(asChatReference({ key: 1, label: "L", prefix: "P" })).toBeNull();
  });

  it("drops a draft that is not text", () => {
    expect(asChatReference({ key: "k", label: "L", prefix: "P", draft: 5 })).toEqual({ key: "k", label: "L", prefix: "P" });
  });
});

describe("approvedGateIn", () => {
  it("knows the wake-up turn of every language", () => {
    expect(GATE_APPROVED_WAKE_TEMPLATES).toEqual(LOCALES.map((l) => dictionary(l).gateApprovedWake));
  });

  it("finds the gate in a wake-up turn, in Finnish or English", () => {
    for (const locale of LOCALES) {
      const text = dictionary(locale).gateApprovedWake.replace("{n}", "2");
      expect(approvedGateIn(text)).toBe(2);
    }
    expect(approvedGateIn("Gate 4 approved in the panel, continue.\n")).toBe(4);
  });

  it("leaves anything the user wrote as their message", () => {
    expect(approvedGateIn("Gate 2 hyväksytty paneelista, jatka. Ja lisää tarkistus.")).toBeNull();
    expect(approvedGateIn("Gate 5 hyväksytty paneelista, jatka.")).toBeNull();
    expect(approvedGateIn("Gate {n} hyväksytty paneelista, jatka.")).toBeNull();
    expect(approvedGateIn("Gate 2 hyväksytty paneelista jatka")).toBeNull();
    expect(approvedGateIn("")).toBeNull();
  });
});
