import { describe, expect, test } from "bun:test";
import {
  conflictKeys,
  followedIds,
  type KnowledgeConflict,
  namesSides,
  resolveConflict,
  resolvedByText,
  sideProblem,
  stillChosen,
  withoutFact,
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

const resolved = (
  over: Partial<KnowledgeConflict> = {},
): KnowledgeConflict => ({
  ...current(),
  description: "The recording says 1998, the document 2005.",
  status: "resolved",
  unit_ids: ["roof-01", "roof-02", "roof-03"],
  preferred_unit_ids: ["roof-01"],
  resolved_by: "primary",
  ...over,
});

describe("withoutFact", () => {
  test("removing the followed fact leaves no deleted id to follow: the conflict is open again", () => {
    const [conflict] = withoutFact([resolved()], "roof-01");

    expect(conflict).toEqual({
      ...resolved(),
      status: "unresolved",
      unit_ids: ["roof-02", "roof-03"],
      preferred_unit_ids: [],
      resolved_by: null,
    });
    expect(followedIds(conflict)).toEqual([]);
  });

  test("removing a fact of the other side keeps the resolution while a side is left", () => {
    const [conflict] = withoutFact([resolved()], "roof-03");

    expect(conflict.status).toBe("resolved");
    expect(conflict.unit_ids).toEqual(["roof-01", "roof-02"]);
    expect(conflict.preferred_unit_ids).toEqual(["roof-01"]);
    expect(conflict.resolved_by).toBe("primary");
  });

  test("a conflict left without another side is no conflict and is dropped", () => {
    const two = resolved({ unit_ids: ["roof-01", "roof-02"] });
    expect(withoutFact([two], "roof-02")).toEqual([]);
    expect(withoutFact([current()], "roof-01")).toEqual([]);
    const sameSide = resolved({ preferred_unit_ids: ["roof-01", "roof-02"] });
    expect(withoutFact([sameSide], "roof-03")).toEqual([]);
  });

  test("conflicts without the fact, and older files, keep their sides", () => {
    const other = { ...current(), unit_ids: ["wall-01", "wall-02"] };
    expect(withoutFact([other], "roof-01")).toEqual([other]);
    const { preferred_unit_ids: _p, resolved_by: _r, ...older } = resolved();
    expect(withoutFact([older], "roof-01")).toEqual([
      { ...older, unit_ids: ["roof-02", "roof-03"] },
    ]);
  });
});

describe("followedIds and resolvedByText", () => {
  test("name the facts a resolved conflict follows and who settled it", () => {
    expect(followedIds(resolved())).toEqual(["roof-01"]);
    expect(resolvedByText(resolved())).toBe("by primary sources");
    expect(resolvedByText(resolved({ resolved_by: "user" }))).toBe("by hand");
  });

  test("say nothing for an open conflict, an older file or ids of other facts", () => {
    expect(followedIds(current())).toEqual([]);
    expect(resolvedByText(current())).toBeNull();
    const { preferred_unit_ids: _p, resolved_by: _r, ...older } = resolved();
    expect(followedIds(older)).toEqual([]);
    expect(resolvedByText(older)).toBeNull();
    expect(followedIds(resolved({ preferred_unit_ids: ["wall-01"] }))).toEqual(
      [],
    );
  });

  test("follow nothing where gaik reads no side chosen: a fact outside the conflict, or every fact", () => {
    // gaik's Conflict._side_named reads both as unresolved.
    const outside = resolved({ preferred_unit_ids: ["roof-01", "ghost"] });
    expect(followedIds(outside)).toEqual([]);
    expect(resolvedByText(outside)).toBeNull();
    const every = resolved({
      unit_ids: ["roof-01", "roof-02"],
      preferred_unit_ids: ["roof-01", "roof-02"],
    });
    expect(followedIds(every)).toEqual([]);
    expect(resolvedByText(every)).toBeNull();
    expect(followedIds(resolved({ unit_ids: [] }))).toEqual([]);
  });
});

describe("an open Settle it card", () => {
  const conflicts = (): KnowledgeConflict[] => [
    { ...current(), topic: "Roof age", unit_ids: ["roof-01", "roof-02"] },
    {
      ...current(),
      topic: "Roof leaks",
      description: "The inspector saw a leak, the seller says none.",
      unit_ids: ["roof-03", "roof-04", "roof-05"],
    },
  ];

  test("keeps its key when an earlier conflict is dropped or one of its facts removed", () => {
    const [, leaks] = conflictKeys(conflicts());
    // Removing roof-01 drops the first conflict; the second moves up a place.
    const dropped = withoutFact(conflicts(), "roof-01");
    expect(dropped.map((c) => c.topic)).toEqual(["Roof leaks"]);
    expect(conflictKeys(dropped)).toEqual([leaks]);
    // Removing one of its own facts leaves it the same card.
    const fewer = withoutFact(conflicts(), "roof-05");
    expect(conflictKeys(fewer)[1]).toBe(leaks);
  });

  test("tells conflicts apart that share a topic and description", () => {
    const twin = conflicts()[0];
    const keys = conflictKeys([
      twin,
      { ...twin, unit_ids: ["roof-06", "roof-07"] },
    ]);
    expect(new Set(keys).size).toBe(2);
  });

  test("forgets a chosen fact that was removed, so the choice can still be saved", () => {
    const leaks = conflicts()[1];
    const chosen = ["roof-03"];
    const [after] = withoutFact([leaks], "roof-03");
    expect(sideProblem(after, chosen)).toContain("only facts of this conflict");
    expect(stillChosen(after, chosen)).toEqual([]);
    expect(stillChosen(after, ["roof-03", "roof-04"])).toEqual(["roof-04"]);
    expect(
      sideProblem(after, stillChosen(after, ["roof-03", "roof-04"])),
    ).toBeNull();
  });
});
