import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "bun:test";
import { reusableSchemaId, savedSchemaKey } from "@/lib/schema-reuse";
import { PARSERS } from "../extractor/extractor-data";
import {
  DEFAULT_OPTIONS,
  EXAMPLES,
  formFields,
  isPageLimited,
  parserAccepts,
  timingText,
} from "./document-data";

const PUBLIC = join(import.meta.dir, "../../../public");
const SCHEMAS = join(import.meta.dir, "../../../api/schemas");

test("every example document exists and names a parser that exists", () => {
  expect(new Set(EXAMPLES.map((e) => e.id)).size).toBe(EXAMPLES.length);
  for (const example of EXAMPLES) {
    expect(existsSync(join(PUBLIC, example.url))).toBe(true);
    expect(PARSERS.map((p) => p.id)).toContain(example.options.parser!);
    expect(parserAccepts(example.options.parser!, example.fileName)).toBe(true);
    expect(example.task.length).toBeGreaterThan(80);
  }
});

test("every example has a saved schema made from exactly its task", () => {
  for (const example of EXAMPLES) {
    const base = join(SCHEMAS, example.schemaKey);
    expect(existsSync(`${base}_schema.py`)).toBe(true);
    const saved = JSON.parse(
      readFileSync(`${base}_requirements.json`, "utf-8"),
    );
    expect(saved.user_requirements.replaceAll("\r\n", "\n").trim()).toBe(
      example.task.trim(),
    );
  }
});

test("the saved schema is used only while the task is unchanged", () => {
  const [report] = EXAMPLES;
  expect(savedSchemaKey(report, report.task)).toBe(report.schemaKey);
  expect(savedSchemaKey(report, `${report.task}\n- Auditor`)).toBe("");
  expect(savedSchemaKey(null, report.task)).toBe("");
  expect(reusableSchemaId({ id: "a", task: "t" }, " t ")).toBe("a");
  expect(reusableSchemaId({ id: "a", task: "t" }, "u")).toBeNull();
});

test("the form carries the parser and the schema choice", () => {
  const fields = (key: string, id: string | null) =>
    Object.fromEntries(
      formFields({ ...DEFAULT_OPTIONS, parser: "vision" }, "task", key, id),
    );
  expect(fields("", null).parser_type).toBe("vision");
  expect(fields("", null).regenerate_schema).toBe("false");
  expect(fields("", "abc").schema_id).toBe("abc");
  expect(fields("saved", "abc").schema_id).toBeUndefined();
  expect(fields("saved", null).schema_key).toBe("saved");
});

test("which parsers read which files", () => {
  expect(parserAccepts("pymupdf", "a.pdf")).toBe(true);
  expect(parserAccepts("pymupdf", "a.png")).toBe(false);
  expect(parserAccepts("docx", "a.docx")).toBe(true);
  expect(parserAccepts("multimodal", "a.jpg")).toBe(false);
  expect(parserAccepts("vision", "a.jpg")).toBe(true);
  expect(isPageLimited("vision_plus")).toBe(true);
  expect(isPageLimited("pymupdf")).toBe(false);
});

test("timings read as one line", () => {
  expect(timingText(null)).toBe("");
  expect(timingText({ parse_s: 2, schema_s: 0, extraction_s: 4.04 })).toBe(
    "parsing 2.0 s · schema 0.0 s · extraction 4.0 s",
  );
});
