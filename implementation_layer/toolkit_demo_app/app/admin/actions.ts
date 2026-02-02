"use server";

import { cookies } from "next/headers";
import { z } from "zod";
import { createServiceClient } from "@/lib/supabase/server";
import { isAdminAuthenticated } from "@/lib/data/admin";

const ADMIN_COOKIE_NAME = "admin_session";
const ADMIN_COOKIE_VALUE = "authenticated";

export type AdminResult = {
  error?: string;
  success?: boolean;
};

const adminPasswordSchema = z.object({
  password: z.string().min(1, "Please enter the admin password."),
});

const updateStatusSchema = z.object({
  userId: z.string().uuid("Invalid user ID."),
  status: z.enum(["approved", "rejected"], {
    message: "Invalid status.",
  }),
});

export async function verifyAdminPassword(
  _prevState: AdminResult,
  formData: FormData,
): Promise<AdminResult> {
  const result = adminPasswordSchema.safeParse({
    password: formData.get("password"),
  });

  if (!result.success) {
    return { error: result.error.issues[0].message };
  }

  const { password } = result.data;

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

export async function adminLogout(): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.delete(ADMIN_COOKIE_NAME);
}

export async function updateAccessStatus(
  userId: string,
  status: "approved" | "rejected",
): Promise<AdminResult> {
  const result = updateStatusSchema.safeParse({ userId, status });
  if (!result.success) {
    return { error: result.error.issues[0].message };
  }

  const isAuthenticated = await isAdminAuthenticated();
  if (!isAuthenticated) {
    return { error: "Unauthorized" };
  }

  const supabase = createServiceClient();

  const { error } = await supabase
    .from("access_requests")
    .update({ status: result.data.status })
    .eq("user_id", result.data.userId);

  if (error) {
    console.error("Failed to update access status:", error);
    return { error: "Failed to update status." };
  }

  return { success: true };
}
