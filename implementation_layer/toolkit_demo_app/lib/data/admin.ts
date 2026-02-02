"use server";

import { cookies } from "next/headers";
import { createServiceClient } from "@/lib/supabase/server";

const ADMIN_COOKIE_NAME = "admin_session";
const ADMIN_COOKIE_VALUE = "authenticated";

export type AccessRequest = {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  company: string | null;
  use_case: string | null;
  status: "pending" | "approved" | "rejected";
  created_at: string;
};

export async function isAdminAuthenticated(): Promise<boolean> {
  const cookieStore = await cookies();
  const adminCookie = cookieStore.get(ADMIN_COOKIE_NAME);
  return adminCookie?.value === ADMIN_COOKIE_VALUE;
}

export async function getAccessRequests(): Promise<AccessRequest[]> {
  const supabase = createServiceClient();

  const { data, error } = await supabase
    .from("access_requests")
    .select("*")
    .order("created_at", { ascending: false });

  if (error) {
    console.error("Failed to fetch access requests:", error);
    return [];
  }

  return data || [];
}
