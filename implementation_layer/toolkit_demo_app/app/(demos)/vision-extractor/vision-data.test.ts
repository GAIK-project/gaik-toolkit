import { expect, test } from "bun:test";
import { existsSync, readFileSync } from "node:fs";
import {
  ACCEPTED_EXTENSIONS,
  EXAMPLES,
  fileNameOf,
  runHint,
  type RunState,
} from "./vision-data";

test("every example file exists in public/ and has an accepted type", () => {
  expect(new Set(EXAMPLES.map((e) => e.id)).size).toBe(EXAMPLES.length);
  for (const example of EXAMPLES) {
    expect(example.files.length).toBeGreaterThan(0);
    for (const file of example.files) {
      expect(existsSync(`public${file.url}`)).toBe(true);
      const ext = `.${fileNameOf(file.url).split(".").pop()}`;
      expect(ACCEPTED_EXTENSIONS).toContain(ext);
    }
  }
});

test("every example has a real task, and the application form comes first", () => {
  expect(EXAMPLES[0].id).toBe("application");
  for (const example of EXAMPLES)
    expect(example.task.length).toBeGreaterThan(300);
});

test("an example is ready-made exactly when its schema folder is committed, made from its task", () => {
  for (const example of EXAMPLES) {
    const folder = `api/schemas/vision_extractor_examples/${example.id}`;
    expect(existsSync(folder)).toBe(example.readyMade);
    if (!example.readyMade) continue;
    for (const name of ["schema.py", "requirements.json", "task.txt"])
      expect(existsSync(`${folder}/${name}`)).toBe(true);
    const saved = readFileSync(`${folder}/task.txt`, "utf-8");
    expect(saved.replaceAll("\r\n", "\n").trim()).toBe(example.task.trim());
    const requirements = JSON.parse(
      readFileSync(`${folder}/requirements.json`, "utf-8"),
    );
    expect(requirements.user_requirements.trim()).toBe(example.task.trim());
  }
});

const idle: RunState = {
  loadingExample: false,
  generatingSchema: false,
  extracting: false,
  fileCount: 1,
  hasTask: true,
  schemaReady: false,
};

test("the run hint names the step that is missing, and keeps the button off", () => {
  expect(runHint({ ...idle, fileCount: 0 })).toEqual({
    ready: false,
    text: "Add at least one document in step 1.",
  });
  expect(runHint({ ...idle, hasTask: false })).toEqual({
    ready: false,
    text: "Say what to extract in step 2.",
  });
  const neither = runHint({ ...idle, fileCount: 0, hasTask: false });
  expect(neither.ready).toBe(false);
  expect(neither.text).toContain("step 1");
  expect(neither.text).toContain("step 2");
});

test("the run hint keeps the button off while anything is running", () => {
  for (const running of [
    { loadingExample: true },
    { generatingSchema: true },
    { extracting: true },
    { extracting: true, generatingSchema: true },
  ])
    expect(runHint({ ...idle, ...running }).ready).toBe(false);
  expect(runHint({ ...idle, extracting: true }).text).toContain("reading");
  expect(
    runHint({ ...idle, extracting: true, generatingSchema: true }).text,
  ).toContain("schema");
});

test("a ready run says whether a schema is generated first, and how many files are read", () => {
  const fresh = runHint(idle);
  expect(fresh.ready).toBe(true);
  expect(fresh.text).toContain("A schema is generated from your text first");
  expect(fresh.text).toContain("reads the file");
  const prepared = runHint({ ...idle, schemaReady: true, fileCount: 3 });
  expect(prepared.ready).toBe(true);
  expect(prepared.text).toContain("The schema is in place");
  expect(prepared.text).toContain("all 3 files");
});
