import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "bun:test";
import {
  DEFAULT_OPTIONS,
  EXAMPLES,
  formFields,
  reusableSchemaId,
  schemaKeyFor,
  timingText,
  transcriptRead,
} from "./audio-data";

const PUBLIC = join(import.meta.dir, "../../../public");

test("every example recording exists", () => {
  for (const example of EXAMPLES)
    expect(existsSync(join(PUBLIC, example.url))).toBe(true);
});

test("examples have unique ids and a task", () => {
  expect(new Set(EXAMPLES.map((e) => e.id)).size).toBe(EXAMPLES.length);
  for (const example of EXAMPLES)
    expect(example.task.length).toBeGreaterThan(40);
});

test("the saved schema is used only while the task is unchanged", () => {
  const [consultation] = EXAMPLES;
  expect(schemaKeyFor(consultation, consultation.task)).toBe(
    "audio_structured_medical_default",
  );
  expect(schemaKeyFor(consultation, `${consultation.task}\n- Allergies`)).toBe(
    "",
  );
  expect(schemaKeyFor(consultation, `  ${consultation.task}  `)).not.toBe("");
  expect(schemaKeyFor(null, "anything")).toBe("");
});

test("the form carries the options", () => {
  const fields = Object.fromEntries(
    formFields(
      {
        ...DEFAULT_OPTIONS,
        language: "fi",
        diarization: true,
        speakers: "2",
        context: " Kometankuja 6 ",
        fixErrors: true,
      },
      "task",
      "",
    ),
  );
  expect(fields.language).toBe("fi");
  expect(fields.diarization).toBe("true");
  expect(fields.min_speakers).toBe("2");
  expect(fields.max_speakers).toBe("2");
  expect(fields.custom_context).toBe("Kometankuja 6");
  expect(fields.fix_transcription_errors).toBe("true");
  expect(fields.regenerate_schema).toBe("false");
});

test("the speaker count is sent only with speaker detection and a number", () => {
  const keys = (options: Partial<typeof DEFAULT_OPTIONS>) =>
    formFields({ ...DEFAULT_OPTIONS, ...options }, "t", "").map(([key]) => key);
  expect(keys({ speakers: "2" })).not.toContain("min_speakers");
  expect(keys({ diarization: true, speakers: "" })).not.toContain(
    "min_speakers",
  );
  expect(keys({ diarization: true, speakers: "x" })).not.toContain(
    "min_speakers",
  );
  expect(keys({ diarization: true, speakers: "3" })).toContain("max_speakers");
  expect(keys({})).not.toContain("custom_context");
});

test("timings read as one line", () => {
  expect(timingText(null)).toBe("");
  expect(
    timingText({ transcription_s: 7, schema_s: 9.84, extraction_s: 7.04 }),
  ).toBe("transcription 7.0 s · schema 9.8 s · extraction 7.0 s");
});

test("the transcript read is the corrected one when there is one", () => {
  expect(
    transcriptRead({ enhanced_transcript: " b ", raw_transcript: "a" }),
  ).toBe("b");
  expect(
    transcriptRead({ enhanced_transcript: null, raw_transcript: "a" }),
  ).toBe("a");
  expect(
    transcriptRead({ enhanced_transcript: null, raw_transcript: null }),
  ).toBe("");
});

test("every example has a saved schema made from exactly its task", () => {
  const schemas = join(import.meta.dir, "../../../api/schemas");
  for (const example of EXAMPLES) {
    expect(example.schemaKey).toBeTruthy();
    const base = join(schemas, example.schemaKey!);
    expect(existsSync(`${base}_schema.py`)).toBe(true);
    const saved = JSON.parse(
      readFileSync(`${base}_requirements.json`, "utf-8"),
    );
    expect(saved.user_requirements.replaceAll("\r\n", "\n").trim()).toBe(
      example.task.trim(),
    );
  }
});

test("the schema of the last run is reused only for the same task", () => {
  const made = { id: "abc", task: "Extract: Title" };
  expect(reusableSchemaId(made, "Extract: Title")).toBe("abc");
  expect(reusableSchemaId(made, "  Extract: Title\n")).toBe("abc");
  expect(reusableSchemaId(made, "Extract: Title, Date")).toBeNull();
  expect(reusableSchemaId(null, "Extract: Title")).toBeNull();
});

test("a schema id is sent only when there is no saved schema key", () => {
  const keys = (key: string, id: string | null) =>
    formFields(DEFAULT_OPTIONS, "t", key, id).map(([name]) => name);
  expect(keys("", "abc")).toContain("schema_id");
  expect(keys("saved_key", "abc")).not.toContain("schema_id");
  expect(keys("", null)).not.toContain("schema_id");
});
