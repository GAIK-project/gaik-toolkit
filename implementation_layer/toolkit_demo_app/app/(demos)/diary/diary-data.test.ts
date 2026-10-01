import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import {
  DEFAULT_FIELD_IDS,
  DIARY_FIELDS,
  composeDiaryPrompt,
  examplePrompt,
  withLanguage,
} from "./diary-data";
import { DIARY_EXAMPLES } from "./diary-examples";

describe("composeDiaryPrompt", () => {
  test("lists the selected fields in the order of the catalogue", () => {
    const prompt = composeDiaryPrompt(["weather", "date"], []);
    expect(prompt.indexOf("- Date")).toBeLessThan(prompt.indexOf("- Weather"));
    expect(prompt).not.toContain("Personnel");
  });

  test("adds own fields, skipping empty names", () => {
    const prompt = composeDiaryPrompt(DEFAULT_FIELD_IDS, [
      { name: " Crane hours ", meaning: "hours the crane was used" },
      { name: "", meaning: "ignored" },
      { name: "Cost", meaning: "" },
    ]);
    expect(prompt).toContain("- Crane hours (hours the crane was used)");
    expect(prompt.endsWith("- Cost")).toBe(true);
    expect(prompt).not.toContain("ignored");
  });

  test("asks for one entry for each day", () => {
    expect(composeDiaryPrompt(["date"], [])).toContain("list called entries");
  });
});

describe("withLanguage", () => {
  test("leaves the prompt alone for the diary's own language", () => {
    expect(withLanguage("x", "Same as the diary")).toBe("x");
  });
  test("adds the language instruction", () => {
    expect(withLanguage("x\n", "Finnish")).toBe(
      "x\nWrite all extracted values in Finnish.",
    );
  });
});

test("every text example has text and every audio example a file", () => {
  for (const example of DIARY_EXAMPLES) {
    if (example.kind === "text")
      expect(example.text?.length).toBeGreaterThan(300);
    else expect(example.audioUrl).toBeTruthy();
  }
});

test("the examples cover English and Finnish", () => {
  const languages = new Set(DIARY_EXAMPLES.map((example) => example.language));
  expect(languages).toEqual(new Set(["English", "Finnish"]));
});

test("the example prompt asks for every field", () => {
  const prompt = examplePrompt();
  for (const field of DIARY_FIELDS)
    expect(prompt).toContain(`- ${field.label} (`);
});

test("the saved example schema was made from the example prompt", () => {
  const file = new URL(
    "../../../api/schemas/construction_diary_example_requirements.json",
    import.meta.url,
  );
  const saved = JSON.parse(readFileSync(file, "utf-8"));
  // Fails when the prompt changes without regenerating and saving the schema again.
  expect(saved.user_requirements).toBe(examplePrompt());
});
