import { type NextRequest, NextResponse } from "next/server";
import { isAdminAuthenticated } from "@/lib/admin/session";

/**
 * GET /api/admin/auth - Check if admin is authenticated
 */
export async function GET(_request: NextRequest) {
  return NextResponse.json({ authenticated: await isAdminAuthenticated() });
}
