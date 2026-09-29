import { expect, test } from "bun:test";
import { unzipSync, strFromU8 } from "fflate";
import {
  ACCEPT,
  buildManifest,
  checkNormalizeForm,
  DEFAULT_OPTIONS,
  FILE_KINDS,
  isSupportedFile,
  MANIFEST_PATH,
  MAX_FILES,
  parseArtifacts,
  readManifest,
  zipArtifacts,
} from "./workspace";

const limits = { maxUploadMb: 1 };

function form(manifest: unknown, files: File[]): FormData {
  const f = new FormData();
  f.append("manifest", typeof manifest === "string" ? manifest : JSON.stringify(manifest));
  for (const file of files) f.append("files", file, file.name);
  return f;
}

const file = (name: string, size = 3) => new File([new Uint8Array(size)], name);

test("buildManifest keeps row order and trims blank options to null", () => {
  const manifest = buildManifest(
    [
      { name: "b.csv", sourceClass: "secondary" },
      { name: "a.txt", sourceClass: "primary" },
    ],
    { transcription_model: "  ", vision_model: " gpt-5.4 ", language: " " },
  );

  expect(manifest.sources.map((s) => s.name)).toEqual(["b.csv", "a.txt"]);
  expect(manifest.options).toEqual({
    transcription_model: null,
    vision_model: "gpt-5.4",
    language: "auto",
  });
});

test("checkNormalizeForm accepts a matching manifest and files", () => {
  const manifest = buildManifest([{ name: "a.txt", sourceClass: "primary" }], DEFAULT_OPTIONS);

  expect(checkNormalizeForm(form(manifest, [file("a.txt")]), limits)).toBeNull();
});

test("checkNormalizeForm refuses malformed requests", () => {
  const one = buildManifest([{ name: "a.txt", sourceClass: "primary" }], DEFAULT_OPTIONS);
  const many = buildManifest(
    Array.from({ length: MAX_FILES + 1 }, (_, i) => ({
      name: `f${i}.txt`,
      sourceClass: "primary" as const,
    })),
    DEFAULT_OPTIONS,
  );

  expect(checkNormalizeForm(new FormData(), limits)?.error).toBe("Missing manifest.");
  expect(checkNormalizeForm(form("{", []), limits)?.error).toBe("Invalid manifest JSON.");
  expect(checkNormalizeForm(form({ sources: [] }, []), limits)?.status).toBe(400);
  expect(checkNormalizeForm(form(many, []), limits)?.error).toContain("Too many files");
  expect(checkNormalizeForm(form(one, []), limits)?.error).toContain("expected 1, got 0");
});

test("checkNormalizeForm enforces the upload limit on file bytes", () => {
  const manifest = buildManifest([{ name: "big.wav", sourceClass: "primary" }], DEFAULT_OPTIONS);
  const refusal = checkNormalizeForm(form(manifest, [file("big.wav", 1024 * 1024 + 1)]), limits);

  expect(refusal).toEqual({ status: 413, error: "Uploads exceed the 1 MB limit." });
  expect(checkNormalizeForm(form(manifest, [file("big.wav", 1024 * 1024)]), limits)).toBeNull();
});

test("parseArtifacts requires the manifest and known paths", () => {
  const ok = { [MANIFEST_PATH]: "[]", "normalized/01_a.md": "text" };

  expect(parseArtifacts(ok)).toEqual(ok);
  expect(() => parseArtifacts({ "normalized/01_a.md": "text" })).toThrow("no normalized/sources.json");
  expect(() => parseArtifacts({ ...ok, "knowledge/x.json": "{}" })).toThrow("Unknown artifact path");
  expect(() => parseArtifacts({ ...ok, "normalized/x.md": 1 })).toThrow("must be text");
  expect(() => parseArtifacts([])).toThrow("mapping path to text");
});

test("readManifest lists the entries and zipArtifacts keeps every path", () => {
  const entries = [
    { id: "01_a", file: "a.txt", source_class: "primary", source_type: "text", tool: "text" },
  ];
  const artifacts = {
    [MANIFEST_PATH]: JSON.stringify(entries),
    "normalized/01_a.md": "Hällo",
  };

  expect(readManifest(artifacts)).toEqual(entries);
  const unzipped = unzipSync(zipArtifacts(artifacts));
  expect(Object.keys(unzipped).sort()).toEqual(["normalized/01_a.md", MANIFEST_PATH]);
  expect(strFromU8(unzipped["normalized/01_a.md"])).toBe("Hällo");
});

test("isSupportedFile matches the converter's types, ignoring case", () => {
  for (const name of ["a.PDF", "b.docx", "c.xlsx", "d.csv", "e.MD", "f.mp4", "g.jpeg"])
    expect(isSupportedFile(name)).toBe(true);
  for (const name of ["a.pptx", "b.doc", "c.xls", "d", ".pdf.bak", "e.zip"])
    expect(isSupportedFile(name)).toBe(false);
});

test("the file picker accepts exactly the listed extensions", () => {
  const listed = FILE_KINDS.flatMap((k) => [...k.extensions]);

  expect(ACCEPT.split(",").sort()).toEqual([...listed].sort());
});
