import { describe, expect, it } from "vitest";
import type { FieldSpec } from "@/components/field-schema-editor";
import {
  buildReadableFields,
  cleanTechnicalWording,
  extractExample,
  extractionProposalHeading,
  extractionProposalStatus,
  missingPolicyText,
} from "@/lib/extraction-proposal";

const fiLabels = {
  heading: "Mitä tietoja poimitaan?",
  headingTicket: "Mitä tietoja tikettiin poimitaan?",
  leftEmpty: "Jätetään tyhjäksi, jos tietoa ei mainita",
  defaultValue: "Oletusarvo: {value}",
  noDefault: "Ei oletusta",
};

describe("extractionProposalHeading", () => {
  it("uses the ticket heading when the solution produces tickets", () => {
    expect(extractionProposalHeading(fiLabels, "MaintenanceTicket", "Huoltotiketti ääniviestistä")).toBe(
      "Mitä tietoja tikettiin poimitaan?",
    );
    expect(extractionProposalHeading(fiLabels, "InvoiceFields", "Laskujen poiminta")).toBe(
      "Mitä tietoja poimitaan?",
    );
  });
});

describe("extractionProposalStatus", () => {
  it("marks an ungenerated prompt proposal after Gate 1 as awaiting approval", () => {
    expect(
      extractionProposalStatus({
        wizardStep: 5,
        gate1Approved: true,
        fieldCount: 4,
        proposal: { promptMarkdown: "## Fields", schemaGenerated: false },
      }),
    ).toBe("awaiting_approval");
  });

  it("marks a generated schema as approved", () => {
    expect(
      extractionProposalStatus({
        wizardStep: 5,
        gate1Approved: true,
        fieldCount: 4,
        proposal: { promptMarkdown: "## Fields", schemaGenerated: true, schemaCode: "class Ticket: ..." },
      }),
    ).toBe("approved");
  });

  it("waits until extraction_requirements.md is written before offering approval on step 5", () => {
    expect(
      extractionProposalStatus({
        wizardStep: 5,
        gate1Approved: true,
        fieldCount: 3,
        proposal: null,
      }),
    ).toBe("none");
  });

  it("stays none before Gate 1 is approved", () => {
    expect(
      extractionProposalStatus({
        wizardStep: 4,
        gate1Approved: false,
        fieldCount: 3,
        proposal: { promptMarkdown: "## Fields", schemaGenerated: false },
      }),
    ).toBe("none");
  });
});

describe("extractExample & cleanTechnicalWording", () => {
  it("separates parenthesised Finnish and English examples from descriptions", () => {
    expect(extractExample("Vikaantuneen laitteen nimi tai tunnus (esim. Pumppu-04, IV-kone 2).")).toEqual({
      cleaned: "Vikaantuneen laitteen nimi tai tunnus.",
      example: "Pumppu-04, IV-kone 2",
    });
    expect(extractExample("Site location (e.g., Building B, 2nd floor)")).toEqual({
      cleaned: "Site location",
      example: "Building B, 2nd floor",
    });
  });

  it("replaces raw null and leave_empty wording", () => {
    const cleaned = cleanTechnicalWording("Jos ei mainita, palauta `null`.", fiLabels.leftEmpty);
    expect(cleaned).not.toContain("null");
    expect(cleaned).toContain("jätetään tyhjäksi");
  });
});

describe("buildReadableFields", () => {
  it("reads human labels and examples from extraction_requirements.md and avoids null jargon", () => {
    const fields: FieldSpec[] = [
      {
        name: "equipment_id",
        type: "text",
        required: true,
        missingBehavior: "empty",
        rule: "Laitteen tunnus tai nimi (esim. Pumppu-04).",
      },
      {
        name: "urgency_level",
        type: "enum",
        allowedValues: ["Kriittinen", "Kiireellinen", "Normaali"],
        required: false,
        missingBehavior: "empty",
        rule: "Kiireellisyys. Jos ei mainita, palauta `null`.",
      },
    ];
    const prompt = [
      "## Kentät",
      "- **Laitteen tunnus** (`equipment_id`): Laitteen nimi tai numero.",
      "- **Kiireellisyys** (`urgency_level`): Arvioitu kiireellisyys. Esimerkki: Kiireellinen",
    ].join("\n");

    const rows = buildReadableFields(fields, null, prompt, fiLabels);
    expect(rows[0]).toMatchObject({
      key: "equipment_id",
      label: "Laitteen tunnus",
      example: "Pumppu-04",
      required: true,
      missingText: fiLabels.leftEmpty,
    });
    expect(rows[1]).toMatchObject({
      key: "urgency_level",
      label: "Kiireellisyys",
      example: "Kiireellinen",
      allowedValues: ["Kriittinen", "Kiireellinen", "Normaali"],
    });
    expect(rows[1].description).not.toContain("null");
  });

  it("maps leave_empty policy to plain missing text", () => {
    expect(missingPolicyText({ missingBehavior: "default" }, "leave_empty", fiLabels)).toBe(fiLabels.leftEmpty);
  });
});
