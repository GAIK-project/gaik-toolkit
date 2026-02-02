import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { createServiceClient } from "@/lib/supabase/server";

const ADMIN_COOKIE_NAME = "admin_session";
const ADMIN_COOKIE_VALUE = "authenticated";

/**
 * GET /api/admin/requests - Get all access requests (admin only)
 */
export async function GET() {
  // Check admin authentication
  const cookieStore = await cookies();
  const adminCookie = cookieStore.get(ADMIN_COOKIE_NAME);
  if (adminCookie?.value !== ADMIN_COOKIE_VALUE) {
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
