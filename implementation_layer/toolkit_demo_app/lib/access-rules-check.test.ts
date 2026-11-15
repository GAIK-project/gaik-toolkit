import { describe, expect, test } from "bun:test";
import {
  type AccessRow,
  type OwnSession,
  checkAccessRules,
} from "./access-rules-check";

const ROW: AccessRow = {
  status: "pending",
  wizard_access: false,
  reports_count: 0,
  report_limit_override: null,
};

/** A table whose rules let the account write when `writable`. */
function table(writable: boolean, visible = 1) {
  let row: AccessRow | null = { ...ROW };
  let inserted = false;
  const session: OwnSession = {
    readOwn: async () => (row ? { ...row } : null),
    countVisible: async () => visible,
    update: async (fields) => {
      if (writable && row) row = { ...row, ...fields };
    },
    insertOwn: async () => {
      inserted = writable;
      return { refused: !writable };
    },
    deleteNone: async () => ({ refused: !writable }),
    restore: async (original) => {
      if (writable) row = { ...original };
    },
  };
  return { session, current: () => row, inserted: () => inserted };
}

describe("checkAccessRules", () => {
  test("passes when the account can only read its own row", async () => {
    const { session } = table(false);
    const results = await checkAccessRules(session);
    expect(results.every((r) => r.ok)).toBe(true);
    expect(results.map((r) => r.name)).toContain(
      "the account cannot change its status",
    );
  });

  test("fails every write check when the rules let the account edit its row, and puts the row back", async () => {
    const t = table(true);
    const results = await checkAccessRules(t.session);
    const failed = results.filter((r) => !r.ok).map((r) => r.name);
    expect(failed).toEqual([
      "the account cannot change its status",
      "the account cannot change its wizard_access",
      "the account cannot change its reports_count",
      "the account cannot change its report_limit_override",
      "the account cannot add a row",
      "the account cannot delete rows",
    ]);
    expect(t.current()).toEqual(ROW);
  });

  test("fails when the account sees rows of other users", async () => {
    const results = await checkAccessRules(table(false, 3).session);
    expect(
      results.find((r) => r.name === "the account sees no other row"),
    ).toMatchObject({ ok: false, detail: "3 rows visible" });
  });

  test("an update that errors counts as refused", async () => {
    const { session } = table(false);
    session.update = async () => {
      throw new Error("permission denied");
    };
    const results = await checkAccessRules(session);
    expect(results.every((r) => r.ok)).toBe(true);
  });
});
