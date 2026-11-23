import { describe, expect, it } from "vitest";
import { FILE_KINDS, fileKind, fileKindInText } from "./file-kind";

describe("fileKind", () => {
  it.each([
    ["use_case.blueprint.json", "json"],
    ["Invoice 2024-03.PDF", "pdf"],
    ["minutes.docx", "word"],
    ["old-contract.doc", "word"],
    ["prices.xlsx", "excel"],
    ["rows.csv", "csv"],
    ["README.md", "markdown"],
    ["src/pipeline/run.py", "python"],
    ["C:\\data\\package.zip", "zip"],
    ["notes.txt", "text"],
    ["meeting.m4a", "audio"],
    ["scan.jpeg", "image"],
  ] as const)("reads %s as %s", (name, kind) => {
    expect(fileKind(name)).toBe(kind);
  });

  it.each([
    ["application/json", "json"],
    ["application/pdf; charset=binary", "pdf"],
    ["application/vnd.openxmlformats-officedocument.wordprocessingml.document", "word"],
    ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "excel"],
    ["text/csv", "csv"],
    ["text/markdown", "markdown"],
    ["text/x-python", "python"],
    ["application/zip", "zip"],
    ["text/plain", "text"],
    ["audio/mpeg", "audio"],
    ["image/png", "image"],
    ["application/problem+json", "json"],
  ] as const)("reads the media type %s as %s", (type, kind) => {
    expect(fileKind(type)).toBe(kind);
  });

  it("goes by the extension of a path that looks like a media type", () => {
    expect(fileKind("notes/summary.md")).toBe("markdown");
    expect(fileKind("text/plan.json")).toBe("json");
  });

  it("has no kind for what it does not know", () => {
    for (const name of ["", "   ", "Dockerfile", ".env", "archive.", "model.bin", "application/octet-stream"]) {
      expect(fileKind(name)).toBeNull();
    }
    expect(fileKind(null)).toBeNull();
    expect(fileKind(undefined)).toBeNull();
  });

  it("knows every kind it names", () => {
    const seen = new Set(
      ["a.json", "a.pdf", "a.docx", "a.xlsx", "a.csv", "a.md", "a.py", "a.zip", "a.txt", "a.wav", "a.png"].map(fileKind),
    );
    expect([...seen].sort()).toEqual([...FILE_KINDS].sort());
  });
});

describe("fileKindInText", () => {
  it("finds the file a line names", () => {
    expect(fileKindInText("Kirjoitetaan output_schema.json")).toBe("json");
    expect(fileKindInText("Reading docs/README.md.")).toBe("markdown");
    expect(fileKindInText("Luetaan Lasku 12.pdf")).toBe("pdf");
  });

  it("finds none in a line without one", () => {
    expect(fileKindInText("Kirjoitetaan ratkaisusuunnitelmaa")).toBeNull();
    expect(fileKindInText("Version 2.1 is ready.")).toBeNull();
    // A longer word that starts like an extension is not a file.
    expect(fileKindInText("See the project.python guide")).toBeNull();
  });
});
