import { describe, expect, test } from "bun:test";
import {
  type KnowledgeConflict,
  namesSides,
  resolveConflict,
  sideProblem,
} from "./conflicts";

const current = (): KnowledgeConflict => ({
  topic: "Roof age",
  description: "The recording says 1998, the document 2005.",
  status: "unresolved",
  unit_ids: ["roof-01", "roof-02"],
  preferred_unit_ids: [],
  resolved_by: null,
});

describe("resolveConflict", () => {
  test("names the chosen fact, so the writer follows it instead of reading it as unresolved", () => {
    const conflict = current();
    resolveConflict(conflict, "Follow the recording.", ["roof-01"]);

    expect(conflict).toEqual({
      topic: "Roof age",
      description: "Follow the recording.",
      status: "resolved",
      unit_ids: ["roof-01", "roof-02"],
      preferred_unit_ids: ["roof-01"],
      resolved_by: "user",
    });
  });

  test("refuses a side that is empty, outside the conflict or every fact", () => {
    expect(sideProblem(current(), [])).toContain("Choose the fact");
    expect(sideProblem(current(), ["roof-09"])).toContain("only facts of this conflict");
    expect(sideProblem(current(), ["roof-01", "roof-02"])).toContain("Leave out at least one");
    const conflict = current();
    expect(() => resolveConflict(conflict, "Follow both.", [])).toThrow("Choose the fact");
    expect(conflict.status).toBe("unresolved");
  });

  test("a file from a gaik without sides keeps its keys: the description gives the side", () => {
    const { preferred_unit_ids: _p, resolved_by: _r, ...older } = current();
    expect(namesSides(older)).toBe(false);
    resolveConflict(older, "Follow the recording.", []);

    expect(older).toEqual({
      topic: "Roof age",
      description: "Follow the recording.",
      status: "resolved",
      unit_ids: ["roof-01", "roof-02"],
    });
  });
});
