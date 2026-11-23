import { describe, expect, it } from "vitest";
import {
  blueprintFileName,
  changedReadonlySection,
  draftText,
  jsonErrorLocation,
  parseDraftText,
  readFullBlueprint,
  readonlyRanges,
  downloadText,
  mergeDrafts,
  withoutAiMark,
} from "@/lib/full-blueprint";
import { AI_RECORD_MARK } from "@/lib/ai-marking";

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

  it("merges the user's change into a draft nobody else changed", () => {
    const mine = { ...draft, models: { extract: { model: "gpt-5-mini" } } };
    expect(mergeDrafts(draft, draft, mine, READONLY)).toEqual({ ok: true, draft: mine });
  });

  it("keeps a section only the newer draft changed, and the user's change beside it", () => {
    const newer = { ...draft, use_case: { id: "invoices", name: "Invoices", description: "by the agent" } };
    const mine = { ...draft, models: { extract: { model: "gpt-5-mini" } } };
    const merged = mergeDrafts(draft, newer, mine, READONLY);
    expect(merged).toEqual({ ok: true, draft: { ...newer, models: { extract: { model: "gpt-5-mini" } } } });
  });

  it("takes a section only the newer draft added or removed", () => {
    const { models: _m, ...newer } = { ...draft, prompts: { extract: "Read the invoice" } };
    void _m;
    const merged = mergeDrafts(draft, newer, draft, READONLY);
    expect(merged.ok && merged.draft).toEqual(newer);
  });

  it("refuses a section both sides changed, and names each one", () => {
    const newer = { ...draft, models: { extract: { model: "gpt-4.1" } }, use_case: { id: "x", name: "Agent's" } };
    const mine = { ...draft, models: { extract: { model: "gpt-5-mini" } }, use_case: { id: "x", name: "Mine" } };
    expect(mergeDrafts(draft, newer, mine, READONLY)).toEqual({ ok: false, conflicts: ["use_case", "models"] });
    // The same change on both sides is no conflict.
    expect(mergeDrafts(draft, newer, newer, READONLY)).toEqual({ ok: true, draft: newer });
  });

  it("takes the read-only sections from the newer draft, always", () => {
    const newer = { ...draft, change_log: [...draft.change_log, { version: "2", change: "agent" }] };
    const mine = { ...draft, change_log: [], package: { name: "p" } };
    const merged = mergeDrafts(draft, newer, mine, READONLY);
    expect(merged.ok && merged.draft.change_log).toEqual(newer.change_log);
    expect(merged.ok && "package" in merged.draft).toBe(false);
  });

  it("marks the download as AI output, and a save never sends the mark", () => {
    const text = downloadText(draft);
    const file = JSON.parse(text) as Record<string, unknown>;
    expect(file).toEqual({ ...AI_RECORD_MARK, ...draft });
    // The mark comes first, where a reader of the file sees it.
    expect(Object.keys(file).slice(0, 2)).toEqual(Object.keys(AI_RECORD_MARK));
    expect(withoutAiMark(file)).toEqual(draft);
    // A draft that already carries the keys gets the mark's own values.
    expect(JSON.parse(downloadText({ ...draft, ai_generated: false }))).toMatchObject(AI_RECORD_MARK);
  });

  it("names the download after the use case", () => {
    expect(blueprintFileName(draft)).toBe("invoices.blueprint.json");
    expect(blueprintFileName({ use_case: { id: "a/b c" } })).toBe("a_b_c.blueprint.json");
    expect(blueprintFileName({})).toBe("blueprint.blueprint.json");
  });
});
