import { describe, expect, it } from "vitest";
import { strFromU8, strToU8, unzipSync, zipSync } from "fflate";
import { attachmentName, zipWithEnv } from "./zip-env";

const PACKAGE = {
  "poc/run_poc.py": strToU8("print('ok')\n"),
  "poc/.env.example": strToU8("A_KEY=\n"),
  "poc/schemas/output_schema.py": strToU8("x = 1\n"),
  "use_case.blueprint.json": strToU8("{}\n"),
  "AI-GENERATED.json": strToU8('{"ai_generated": true}\n'),
};

describe("zipWithEnv", () => {
  it("adds poc/.env and keeps every other entry as it was", async () => {
    const out = unzipSync(await zipWithEnv(zipSync(PACKAGE), "A_KEY=typed\n"));

    expect(Object.keys(out).sort()).toEqual([...Object.keys(PACKAGE), "poc/.env"].sort());
    expect(strFromU8(out["poc/.env"])).toBe("A_KEY=typed\n");
    for (const [name, bytes] of Object.entries(PACKAGE)) {
      expect(strFromU8(out[name])).toBe(strFromU8(bytes));
    }
  });

  it("replaces a .env the zip already had", async () => {
    const zip = zipSync({ ...PACKAGE, "poc/.env": strToU8("OLD=1\n") });

    const out = unzipSync(await zipWithEnv(zip, "NEW=2\n"));

    expect(strFromU8(out["poc/.env"])).toBe("NEW=2\n");
  });

  it("refuses bytes that are not a zip", async () => {
    await expect(zipWithEnv(strToU8("<html>not a zip</html>"), "A=1\n")).rejects.toThrow();
  });
});

describe("attachmentName", () => {
  it("reads the name the server gave and falls back without one", () => {
    expect(attachmentName('attachment; filename="poc-1-deployable.zip"', "x.zip")).toBe("poc-1-deployable.zip");
    expect(attachmentName(null, "x.zip")).toBe("x.zip");
    expect(attachmentName('attachment; filename="../evil.zip"', "x.zip")).toBe("x.zip");
  });
});
