import { describe, expect, it } from "vitest";
import { dictionary, LOCALES } from "./i18n";
import { plainLabel, plainLabelCapitalized, plainLabels } from "./plain-label";

describe("plainLabel", () => {
  const labels = { knowledge_capture: "tiedon tallentaminen" };

  it("gives a known value its label, however the agent spelled it", () => {
    expect(plainLabel("knowledge_capture", labels)).toBe("tiedon tallentaminen");
    expect(plainLabel(" Knowledge-Capture ", labels)).toBe("tiedon tallentaminen");
    expect(plainLabel("knowledge capture", labels)).toBe("tiedon tallentaminen");
  });

  it("shows an unknown identifier as words, never as a snake_case token", () => {
    expect(plainLabel("data_retention_policy", labels)).toBe("data retention policy");
    expect(plainLabel("toString", labels)).toBe("toString");
  });

  it("leaves ordinary text as it was written", () => {
    expect(plainLabel("Invoice review", labels)).toBe("Invoice review");
    expect(plainLabel("Finance")).toBe("Finance");
    expect(plainLabel("Asiakas- ja laskutusdata")).toBe("Asiakas- ja laskutusdata");
  });

  it("keeps the hyphen of a real word", () => {
    expect(plainLabel("HR-hallinto")).toBe("HR-hallinto");
    expect(plainLabelCapitalized("e-lasku")).toBe("E-lasku");
    expect(plainLabel("invoice-processing")).toBe("invoice-processing");
    // Underscores still go, and a hyphen beside them stays.
    expect(plainLabel("hr-hallinto_2026")).toBe("hr-hallinto 2026");
  });

  it("capitalizes a value that stands alone", () => {
    expect(plainLabelCapitalized("knowledge_capture", labels)).toBe("Tiedon tallentaminen");
    expect(plainLabelCapitalized("älykäs_haku")).toBe("Älykäs haku");
  });

  it("drops a label that two identifiers share", () => {
    expect(plainLabels(["docx", "word_document", "pdf"], { docx: "Word", word_document: "Word" })).toEqual([
      "Word",
      "pdf",
    ]);
  });
});

describe("the dictionaries' identifier labels", () => {
  // The values the wizard's skill and blueprint schema define.
  const KNOWLEDGE_PROCESSES = ["knowledge_capture", "knowledge_access", "knowledge_synthesis"];
  const IMPACTS = ["component_selection", "workflow_design", "security_constraint", "schema", "low", "medium", "high"];

  for (const locale of LOCALES) {
    const t = dictionary(locale);
    it(`${locale}: names every known knowledge process and impact`, () => {
      for (const value of KNOWLEDGE_PROCESSES) {
        expect(t.bcKnowledgeProcessLabels[value], value).toBeTruthy();
      }
      for (const value of IMPACTS) {
        expect(t.asmImpactLabels[value], value).toBeTruthy();
      }
    });
    it(`${locale}: no label is itself an identifier`, () => {
      const all = [...Object.values(t.bcKnowledgeProcessLabels), ...Object.values(t.asmImpactLabels)];
      for (const label of all) expect(label).not.toMatch(/_/);
    });
  }
});
