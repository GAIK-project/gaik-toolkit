import { describe, expect, it } from "vitest";
import {
  blueprintFileName,
  changedReadonlySection,
  draftText,
  jsonErrorLocation,
  parseDraftText,
  readFullBlueprint,
  readonlyRanges,
  withServerSections,
} from "@/lib/full-blueprint";

const READONLY = ["blueprint_version", "metadata", "visualizations", "package", "traceability", "change_log"];

const draft = {
  blueprint_version: "1.0",
  metadata: { blueprint_id: "bp", status: "draft" },
  use_case: { id: "invoices", name: "Invoices" },
  models: { extract: { model: "gpt-4.1-mini" } },
  change_log: [{ version: "1", change: "first" }],
};

describe("full blueprint", () => {
  it("reads the GET answer, and nothing that is not one", () => {
    expect(
      readFullBlueprint({ version: 3, draft, draft_digest: "abc", readonly_sections: READONLY }),
    ).toEqual({ version: 3, draft, draftDigest: "abc", readonlySections: READONLY });
    expect(readFullBlueprint({ version: 3, draft: [], draft_digest: "abc" })).toBeNull();
    expect(readFullBlueprint({ draft, draft_digest: "abc" })).toBeNull();
    expect(readFullBlueprint(null)).toBeNull();
  });

  it("marks each read-only section's property in the text, and only those", () => {
    const text = draftText(draft);
    const ranges = readonlyRanges(text, READONLY);
    const shown = ranges.map((r) => text.slice(r.from, r.to));
    expect(shown).toEqual([
      '"blueprint_version": "1.0"',
      `"metadata": ${JSON.stringify(draft.metadata, null, 2).replace(/\n/g, "\n  ")}`,
      `"change_log": ${JSON.stringify(draft.change_log, null, 2).replace(/\n/g, "\n  ")}`,
    ]);
    // A nested key of the same name is not a section.
    const nested = draftText({ use_case: { id: "x", metadata: { a: 1 } } });
    expect(readonlyRanges(nested, READONLY)).toEqual([]);
  });

  it("says where JSON that does not parse goes wrong, by line and column", () => {
    expect(parseDraftText('{\n  "a": x\n}')).toEqual({ ok: false, line: 2, column: 8 });
    expect(parseDraftText('{\n  "a": 1,\n}')).toEqual({ ok: false, line: 3, column: 1 });
    expect(parseDraftText('{\n  "a": 1\n  "b": 2\n}')).toEqual({ ok: false, line: 3, column: 3 });
    expect(parseDraftText("")).toEqual({ ok: false, line: 1, column: 1 });
    expect(parseDraftText("[1]")).toEqual({ ok: false, line: null, column: null, notObject: true });
    expect(parseDraftText('{"a": "\u00e4"}')).toEqual({ ok: true, draft: { a: "ä" } });
    expect(jsonErrorLocation('{"a": [1, 2,]}')).toBe(12);
    expect(jsonErrorLocation('{"a": 1}')).toBe(-1);
  });

  it("finds a read-only section the text changed, whatever the order of keys", () => {
    const edited = { ...draft, metadata: { status: "draft", blueprint_id: "bp" }, models: { extract: { model: "x" } } };
    expect(changedReadonlySection(draft, edited, READONLY)).toBeNull();
    expect(changedReadonlySection(draft, { ...draft, metadata: { blueprint_id: "other" } }, READONLY)).toBe(
      "metadata",
    );
    const { change_log: _dropped, ...withoutLog } = draft;
    void _dropped;
    expect(changedReadonlySection(draft, withoutLog, READONLY)).toBe("change_log");
    expect(changedReadonlySection(draft, { ...draft, package: { name: "p" } }, READONLY)).toBe("package");
  });

  it("takes the read-only sections from the server's draft for a save", () => {
    const newer = { ...draft, change_log: [...draft.change_log, { version: "2", change: "agent" }] };
    const { visualizations: _v, ...base } = { ...newer, visualizations: undefined };
    void _v;
    const edited = { ...draft, models: { extract: { model: "gpt-5-mini" } }, visualizations: { a: 1 } };
    const sent = withServerSections(edited, base, READONLY);
    expect(sent.change_log).toEqual(newer.change_log);
    expect(sent.models).toEqual({ extract: { model: "gpt-5-mini" } });
    expect("visualizations" in sent).toBe(false);
  });

  it("names the download after the use case", () => {
    expect(blueprintFileName(draft)).toBe("invoices.blueprint.json");
    expect(blueprintFileName({ use_case: { id: "a/b c" } })).toBe("a_b_c.blueprint.json");
    expect(blueprintFileName({})).toBe("blueprint.blueprint.json");
  });
});
