import { NextResponse } from "next/server";
import { createServiceClient } from "@/lib/supabase/server";
import { isAdminAuthenticated } from "@/lib/admin/session";
import { readWizardUse } from "@/lib/wizard-usage";

/**
 * GET /api/admin/requests - Get all access requests (admin only)
 *
 * A row that holds the first wizard's grant also carries `wizard_use`: the
 * sessions and messages counted for that user (lib/wizard-usage.ts), or null
 * when nothing is counted.
 */
export async function GET() {
  if (!(await isAdminAuthenticated())) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const supabase = createServiceClient();

  const { data, error } = await supabase
    .from("access_requests")
    .select("*")
    .order("created_at", { ascending: false });

  if (error) {
    console.error("Failed to fetch access requests:", error);
    return NextResponse.json(
      { error: "Failed to fetch access requests" },
      { status: 500 },
    );
  }

  const rows = data || [];
  const use = await readWizardUse(
    rows.filter((row) => row.wizard_access === true).map((row) => row.user_id),
  );
  return NextResponse.json(
    rows.map((row) => ({ ...row, wizard_use: use?.[row.user_id] ?? null })),
  );
}
