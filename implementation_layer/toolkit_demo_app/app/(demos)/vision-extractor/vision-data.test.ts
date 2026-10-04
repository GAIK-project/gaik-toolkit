import { expect, test } from "bun:test";
import { existsSync, readFileSync } from "node:fs";
import { ACCEPTED_EXTENSIONS, EXAMPLES, fileNameOf } from "./vision-data";

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
