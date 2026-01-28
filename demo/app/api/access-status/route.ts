import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

export async function GET() {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ status: null }, { status: 401 });
  }

  const { data: accessRequest } = await supabase
    .from("access_requests")
    .select("status")
    .eq("user_id", user.id)
    .single();

  return NextResponse.json({ status: accessRequest?.status ?? "pending" });
}
