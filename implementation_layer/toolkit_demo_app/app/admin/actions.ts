"use server";

import { cookies } from "next/headers";
import { createServiceClient } from "@/lib/supabase/server";

const ADMIN_COOKIE_NAME = "admin_session";
const ADMIN_COOKIE_VALUE = "authenticated";

export type AdminResult = {
  error?: string;
  success?: boolean;
};

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

export async function verifyAdminPassword(
  _prevState: AdminResult,
  formData: FormData,
): Promise<AdminResult> {
  const password = formData.get("password") as string;

  if (!password) {
    return { error: "Please enter the admin password." };
  }

  const adminPassword = process.env.ADMIN_PASSWORD;
  if (!adminPassword) {
    console.error("ADMIN_PASSWORD environment variable is not set");
    return { error: "Admin access is not configured." };
  }

  if (password !== adminPassword) {
    return { error: "Invalid password." };
  }

  const cookieStore = await cookies();
  cookieStore.set(ADMIN_COOKIE_NAME, ADMIN_COOKIE_VALUE, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: 60 * 60 * 8, // 8 hours
  });

  return { success: true };
}

export async function isAdminAuthenticated(): Promise<boolean> {
  const cookieStore = await cookies();
  const adminCookie = cookieStore.get(ADMIN_COOKIE_NAME);
  return adminCookie?.value === ADMIN_COOKIE_VALUE;
}

export async function adminLogout(): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.delete(ADMIN_COOKIE_NAME);
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

export async function updateAccessStatus(
  userId: string,
  status: "approved" | "rejected",
): Promise<AdminResult> {
  const isAuthenticated = await isAdminAuthenticated();
  if (!isAuthenticated) {
    return { error: "Unauthorized" };
  }

  const supabase = createServiceClient();

  const { error } = await supabase
    .from("access_requests")
    .update({ status })
    .eq("user_id", userId);

  if (error) {
    console.error("Failed to update access status:", error);
    return { error: "Failed to update status." };
  }

  return { success: true };
}
