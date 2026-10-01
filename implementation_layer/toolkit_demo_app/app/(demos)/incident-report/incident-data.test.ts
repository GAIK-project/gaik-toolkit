import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { INCIDENT_EXAMPLES } from "./incident-examples";
import {
  DEFAULT_FIELD_IDS,
  INCIDENT_FIELDS,
  examplePrompt,
  composeIncidentPrompt,
  withLanguage,
} from "./incident-data";

describe("composeIncidentPrompt", () => {
  test("lists the selected fields in the order of the catalogue", () => {
    const prompt = composeIncidentPrompt(["location", "date"], []);
    expect(prompt.indexOf("- Date")).toBeLessThan(prompt.indexOf("- Location"));
    expect(prompt).not.toContain("Injuries");
  });

  test("adds own fields, skipping empty names", () => {
    const prompt = composeIncidentPrompt(DEFAULT_FIELD_IDS, [
      { name: " Shift ", meaning: "day or night" },
      { name: "", meaning: "ignored" },
      { name: "Cost", meaning: "" },
    ]);
    expect(prompt).toContain("- Shift (day or night)");
    expect(prompt.endsWith("- Cost")).toBe(true);
    expect(prompt).not.toContain("ignored");
  });

  test("asks for each incident separately", () => {
    expect(composeIncidentPrompt(["date"], [])).toContain(
      "list called incidents",
    );
  });
});

describe("withLanguage", () => {
  test("leaves the prompt alone for the report's own language", () => {
    expect(withLanguage("x", "Same as the report")).toBe("x");
  });
  test("adds the language instruction", () => {
    expect(withLanguage("x\n", "Finnish")).toBe(
      "x\nWrite all extracted values in Finnish.",
    );
  });
});

test("every text example has text and every audio example a file", () => {
  for (const example of INCIDENT_EXAMPLES) {
    if (example.kind === "text")
      expect(example.text?.length).toBeGreaterThan(50);
    else expect(example.audioUrl).toBeTruthy();
  }
});

test("the example prompt asks for every field", () => {
  const prompt = examplePrompt();
  for (const field of INCIDENT_FIELDS)
    expect(prompt).toContain(`- ${field.label} (`);
});

test("the examples cover English and Finnish", () => {
  const languages = new Set(
    INCIDENT_EXAMPLES.map((example) => example.language),
  );
  expect(languages).toEqual(new Set(["English", "Finnish"]));
});

test("the saved example schema was made from the example prompt", () => {
  const file = new URL(
    "../../../api/schemas/incident_report_example_requirements.json",
    import.meta.url,
  );
  const saved = JSON.parse(readFileSync(file, "utf-8"));
  // Fails when the prompt changes without regenerating and saving the schema again.
  expect(saved.user_requirements).toBe(examplePrompt());
});
