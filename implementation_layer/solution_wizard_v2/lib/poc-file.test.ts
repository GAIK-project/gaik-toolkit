import { describe, expect, it } from "vitest";
import {
  editorLanguage,
  isSecretEnvName,
  pocFileAffectsPackage,
  pocFileFrom,
  pocFileReadOnly,
  pocFileSavedFrom,
  pocPathOf,
  utf8Bytes,
} from "./poc-file";

describe("pocPathOf", () => {
  it("is the path inside poc/, and null for what lies beside it", () => {
    expect(pocPathOf("poc/run_poc.py")).toBe("run_poc.py");
    expect(pocPathOf("poc/schemas/output_schema.py")).toBe("schemas/output_schema.py");
    expect(pocPathOf("use_case.blueprint.json")).toBeNull();
    expect(pocPathOf("docs/user_guide.md")).toBeNull();
    expect(pocPathOf("poc/")).toBeNull();
  });
});

describe("isSecretEnvName", () => {
  it("is every .env and *.env name but .env.example, in any folder and case", () => {
    for (const name of [
      ".env",
      ".env.local",
      ".ENV",
      "config/.env",
      ".env.production",
      ".envrc",
      "prod.env",
      "config/local.env",
      "Keys.ENV",
    ]) {
      expect(isSecretEnvName(name), name).toBe(true);
    }
    for (const name of [".env.example", "config/.env.example", "env.py", "environment.yaml", "prod.env.md"]) {
      expect(isSecretEnvName(name), name).toBe(false);
    }
  });
});

describe("pocFileReadOnly", () => {
  it("lets text files of the package and .env.example be edited", () => {
    for (const path of ["run_poc.py", "README.md", "config.yaml", "schemas/x.json", "pages/a.html", ".env.example"]) {
      expect(pocFileReadOnly(path), path).toBeNull();
    }
  });

  it("keeps the marker, the test material and a run's output read-only, and other types uneditable", () => {
    expect(pocFileReadOnly("AI-GENERATED.json")).toBe("file_read_only");
    expect(pocFileReadOnly("sample_input/note.txt")).toBe("file_read_only");
    expect(pocFileReadOnly("output/result.json")).toBe("file_read_only");
    expect(pocFileReadOnly("Dockerfile")).toBe("file_type_not_editable");
    expect(pocFileReadOnly("logo.png")).toBe("file_type_not_editable");
  });

  it("keeps the package's test page read-only: app.py at the root and everything under ui/", () => {
    expect(pocFileReadOnly("app.py")).toBe("file_read_only");
    expect(pocFileReadOnly("ui/index.html")).toBe("file_read_only");
    expect(pocFileReadOnly("ui/solution.json")).toBe("file_read_only");
    expect(pocFileReadOnly("helpers/app.py")).toBeNull();
  });

  it("keeps a file in a hidden folder or __pycache__ read-only: the digest leaves those out", () => {
    expect(pocFileReadOnly(".streamlit/config.toml")).toBe("file_read_only");
    expect(pocFileReadOnly("helpers/__pycache__/notes.txt")).toBe("file_read_only");
    expect(pocFileReadOnly(".env.example")).toBeNull();
  });
});

describe("pocFileAffectsPackage", () => {
  it("is every file the editor saves but a README, as wizard_api's digest is", () => {
    for (const path of ["run_poc.py", "app.py", "labels.json", ".env.example", "notes.txt", "prompts/README.md"]) {
      expect(pocFileAffectsPackage(path), path).toBe(true);
    }
    for (const path of [
      "README.md",
      "helpers/Readme.md",
      "ui/index.html",
      "AI-GENERATED.json",
      "sample_input/a.txt",
      ".cache/x.py",
    ]) {
      expect(pocFileAffectsPackage(path), path).toBe(false);
    }
  });
});

describe("editorLanguage", () => {
  it("follows the file's name", () => {
    expect(editorLanguage("run_poc.py")).toBe("python");
    expect(editorLanguage("config.yml")).toBe("yaml");
    expect(editorLanguage("schemas/a.JSON")).toBe("json");
    expect(editorLanguage(".env.example")).toBe("properties");
    expect(editorLanguage("pyproject.toml")).toBe("toml");
    expect(editorLanguage("notes.txt")).toBeNull();
    expect(editorLanguage("Dockerfile")).toBeNull();
  });
});

describe("the api's answers", () => {
  it("are read into the app's own shape, and refused when a part is missing", () => {
    expect(
      pocFileFrom({
        path: "run_poc.py",
        content: "x",
        digest: "d",
        editable: true,
        read_only_reason: null,
        affects_package: true,
      }),
    ).toEqual({
      path: "run_poc.py",
      content: "x",
      digest: "d",
      editable: true,
      readOnlyReason: null,
      affectsPackage: true,
    });
    expect(pocFileFrom({ path: "run_poc.py", digest: "d" })).toBeNull();
    expect(pocFileFrom("<html>")).toBeNull();
    expect(pocFileSavedFrom({ path: "a.py", digest: "d2", gate_reopened: "gate_3", affects_package: true })).toEqual({
      path: "a.py",
      digest: "d2",
      gateReopened: "gate_3",
      affectsPackage: true,
    });
    expect(pocFileSavedFrom({ path: "a.py" })).toBeNull();
  });

  it("counts a file's size in bytes, as the api does", () => {
    expect(utf8Bytes("ää")).toBe(4);
  });
});
