import { expect, test } from "bun:test";
import { existsSync } from "node:fs";
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
