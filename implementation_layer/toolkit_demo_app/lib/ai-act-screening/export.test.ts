import { describe, expect, test } from "bun:test";
import { screeningToMarkdown } from "./export";
import { conditionText, isCurrentGap, type Screening } from "./types";

const screening: Screening = {
  screened_on: "2026-11-16",
  reference_last_verified: "2026-11-16",
  summary: {
    outcome: "classified",
    risk_class: "high",
    role: "deployer",
    confidence: "medium",
    mode: "existing",
    lifecycle_stage: "production",
    screened_use: "A CV scoring tool.",
    one_line: "Ranks job applicants.",
    flags: { art_6_3_exempt: false, transparency_duties: false },
  },
  findings: [
    {
      id: "F5",
      question: "q",
      status: "yes",
      answer: "Yes.",
      evidence: [
        { source: "description", locator: "description", quote: "It ranks." },
      ],
      citations: [{ ref: "Annex III(4)(a)" }],
      reasoning: "Because.",
      confidence: "high",
    },
  ],
  actions: [
    {
      type: "required",
      action: "Inform applicants | in writing.",
      route: "organisation",
      applies_from: "2025-02-02",
      citations: [{ ref: "Art. 4" }],
      based_on: ["F5"],
      status: "missing",
    },
    {
      type: "required",
      action: "Later duty.",
      route: "system",
      applies_from: "2027-12-02",
      based_on: ["F5"],
      status: "missing",
    },
  ],
  timeline: [],
  triggers: [],
  open_questions: [],
  adjacent: [],
  disclaimer: "Preliminary.",
};

describe("isCurrentGap", () => {
  test("only a missing duty whose date has passed is a gap", () => {
    expect(isCurrentGap(screening.actions[0], screening.screened_on)).toBe(
      true,
    );
    expect(isCurrentGap(screening.actions[1], screening.screened_on)).toBe(
      false,
    );
  });
});

describe("screeningToMarkdown", () => {
  const md = screeningToMarkdown(screening, "CV tool");

  test("opens with the name and the summary", () => {
    expect(md).toContain("# EU AI Act screening: CV tool");
    expect(md).toContain("Ranks job applicants.");
  });

  test("shows the tier in plain words and the current gap", () => {
    expect(md).toContain("**Risk tier:** High-risk.");
    expect(md).toContain("## Current gaps");
  });

  test("keeps table cells on one row", () => {
    expect(md).toContain("Inform applicants \\| in writing.");
  });

  test("never leaks data codes", () => {
    expect(md).not.toMatch(/\bin_place\b|\bF5\b|risk_class/);
  });
});

test("an alternative's condition reads once after If", () => {
  expect(conditionText("If an applicable prohibited practice applies.")).toBe(
    "an applicable prohibited practice applies",
  );
  expect(conditionText("the system ranks job applicants")).toBe(
    "the system ranks job applicants",
  );
  expect(conditionText("  if it profiles people .. ")).toBe(
    "it profiles people",
  );
});
