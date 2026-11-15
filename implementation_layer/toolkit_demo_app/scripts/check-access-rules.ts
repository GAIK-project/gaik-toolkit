// Checks the access rules of the demo's access_requests table against the real
// Supabase project, with a test account's own session
// (supabase/access_requests_rules.sql, lib/access-rules-check.ts).
//
// Use an account made for this check, pending and not an administrator: when a
// rule is missing the check changes the account's row and then puts it back
// (a row it could add is left for removal in the dashboard; the output says so).
//
//   NEXT_PUBLIC_SUPABASE_URL=... NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=... \
//   ACCESS_CHECK_EMAIL=... ACCESS_CHECK_PASSWORD=... \
//   bun scripts/check-access-rules.ts
//
// Exits 1 when any check fails.

import { createClient } from "@supabase/supabase-js";
import {
  type AccessRow,
  type OwnSession,
  checkAccessRules,
} from "../lib/access-rules-check";

const FIELDS = "status, wizard_access, reports_count, report_limit_override";

function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    console.error(`${name} is not set`);
    process.exit(2);
  }
  return value;
}

const supabase = createClient(
  required("NEXT_PUBLIC_SUPABASE_URL"),
  required("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"),
  { auth: { persistSession: false, autoRefreshToken: false } },
);

const { data: signIn, error: signInError } =
  await supabase.auth.signInWithPassword({
    email: required("ACCESS_CHECK_EMAIL"),
    password: required("ACCESS_CHECK_PASSWORD"),
  });
if (signInError || !signIn.user) {
  console.error("Sign-in with the test account failed");
  process.exit(2);
}
const userId = signIn.user.id;
const own = () =>
  supabase.from("access_requests").select(FIELDS).eq("user_id", userId);

const session: OwnSession = {
  readOwn: async () => {
    const { data } = await own().maybeSingle();
    return (data as AccessRow | null) ?? null;
  },
  countVisible: async () => {
    const { count } = await supabase
      .from("access_requests")
      .select("user_id", { count: "exact", head: true });
    return count ?? 0;
  },
  update: async (fields) => {
    await supabase.from("access_requests").update(fields).eq("user_id", userId);
  },
  insertOwn: async () => {
    const { error } = await supabase.from("access_requests").insert({
      user_id: userId,
      email: "access-check@example.com",
      full_name: "Access check",
      status: "approved",
    });
    return { refused: !!error };
  },
  deleteNone: async () => {
    const { error } = await supabase
      .from("access_requests")
      .delete()
      .eq("user_id", userId)
      .eq("status", "access-check: no row has this status");
    return { refused: !!error };
  },
  restore: async (row) => {
    await supabase.from("access_requests").update(row).eq("user_id", userId);
  },
};

const results = await checkAccessRules(session);
await supabase.auth.signOut();
for (const r of results)
  console.log(
    `${r.ok ? "ok  " : "FAIL"} ${r.name}${r.detail ? ` (${r.detail})` : ""}`,
  );
process.exit(results.every((r) => r.ok) ? 0 : 1);
