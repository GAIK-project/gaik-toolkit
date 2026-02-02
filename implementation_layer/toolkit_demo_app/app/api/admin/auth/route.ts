import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const ADMIN_COOKIE_NAME = "admin_session";
const ADMIN_COOKIE_VALUE = "authenticated";

/**
 * GET /api/admin/auth - Check if admin is authenticated
 */
export async function GET() {
  const cookieStore = await cookies();
  const adminCookie = cookieStore.get(ADMIN_COOKIE_NAME);
  const isAuthenticated = adminCookie?.value === ADMIN_COOKIE_VALUE;

  return NextResponse.json({ authenticated: isAuthenticated });
}
