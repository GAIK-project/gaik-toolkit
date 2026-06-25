import { NextResponse, type NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/middleware";
import { DEV_AUTH, DEV_COOKIE } from "@/lib/auth";

export async function middleware(request: NextRequest) {
  // Dev mode: simple cookie check, no Supabase.
  if (DEV_AUTH) {
    const hasSession = request.cookies.has(DEV_COOKIE);
    if (!hasSession && !request.nextUrl.pathname.startsWith("/login")) {
      const url = request.nextUrl.clone();
      url.pathname = "/login";
      return NextResponse.redirect(url);
    }
    return NextResponse.next();
  }

  // Production path: Supabase session refresh + route protection.
  return await updateSession(request);
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
