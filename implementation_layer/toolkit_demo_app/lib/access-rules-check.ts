// Checks, with a signed-in test account's own session, that the account cannot
// change its access_requests row (supabase/access_requests_rules.sql): not its
// approval status, its Solution Wizard flag, its report counter or its report
// cap. Run by scripts/check-access-rules.ts against the demo's Supabase project.

export interface AccessRow {
  status: string;
  wizard_access: boolean | null;
  reports_count: number | null;
  report_limit_override: number | null;
}

/** The account's view of the table through its own session. */
export interface OwnSession {
  readOwn(): Promise<AccessRow | null>;
  countVisible(): Promise<number>;
  update(fields: Partial<AccessRow>): Promise<void>;
  /** Insert a second, approved row for the account itself. */
  insertOwn(): Promise<{ refused: boolean }>;
  /**
   * Delete with a condition no row meets: refused without the table's delete
   * privilege, and deletes nothing with it, so the account's row is never lost.
   */
  deleteNone(): Promise<{ refused: boolean }>;
  restore(row: AccessRow): Promise<void>;
}

export interface CheckResult {
  name: string;
  ok: boolean;
  detail?: string;
}

/** A change to each server-owned field, away from its current value. */
function changes(row: AccessRow): [keyof AccessRow, Partial<AccessRow>][] {
  return [
    ["status", { status: row.status === "approved" ? "pending" : "approved" }],
    ["wizard_access", { wizard_access: !row.wizard_access }],
    [
      "reports_count",
      { reports_count: (row.reports_count ?? 0) === 0 ? 1 : 0 },
    ],
    [
      "report_limit_override",
      {
        report_limit_override:
          row.report_limit_override === 1_000_000 ? 0 : 1_000_000,
      },
    ],
  ];
}

export async function checkAccessRules(
  session: OwnSession,
): Promise<CheckResult[]> {
  const results: CheckResult[] = [];
  const original = await session.readOwn();
  results.push({ name: "the account reads its own row", ok: !!original });
  if (!original) return results;

  const visible = await session.countVisible();
  results.push({
    name: "the account sees no other row",
    ok: visible === 1,
    detail: `${visible} rows visible`,
  });

  for (const [field, change] of changes(original)) {
    await session.update(change).catch(() => undefined);
    const after = await session.readOwn();
    const changed = !after || after[field] !== original[field];
    if (changed) await session.restore(original).catch(() => undefined);
    results.push({
      name: `the account cannot change its ${field}`,
      ok: !changed,
      detail: changed
        ? `${field} changed to ${String(after?.[field])}`
        : undefined,
    });
  }

  // A row for another user would fail on the foreign key to auth.users whatever
  // the rules say, so the check adds a second row for the account itself.
  const insert = await session.insertOwn();
  results.push({
    name: "the account cannot add a row",
    ok: insert.refused,
    detail: insert.refused
      ? undefined
      : "an approved row was added for the test account; remove it in the dashboard",
  });

  // Deleting the row itself could not be undone with the account's session (an
  // update does not bring back a deleted row), so the check asks only whether a
  // delete is refused, with a condition that matches no row.
  const deletion = await session
    .deleteNone()
    .catch(() => ({ refused: true }));
  results.push({
    name: "the account cannot delete rows",
    ok: deletion.refused,
    detail: deletion.refused
      ? undefined
      : "the table still grants delete to signed-in users",
  });

  return results;
}
