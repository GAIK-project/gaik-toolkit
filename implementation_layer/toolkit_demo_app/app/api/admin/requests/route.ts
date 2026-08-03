import { NextResponse } from "next/server";
import { createServiceClient } from "@/lib/supabase/server";
import { isAdminAuthenticated } from "@/lib/admin/session";

/**
 * GET /api/admin/requests - Get all access requests (admin only)
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

  return NextResponse.json(data || []);
}
