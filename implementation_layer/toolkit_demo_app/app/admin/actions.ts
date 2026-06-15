"use server";

import { cookies } from "next/headers";
import { z } from "zod";
import { createServiceClient } from "@/lib/supabase/server";
import { getReportWriterLimits } from "@/lib/report-writer/limits";

const ADMIN_COOKIE_NAME = "admin_session";
const ADMIN_COOKIE_VALUE = "authenticated";

async function isAdminAuthenticated(): Promise<boolean> {
  const cookieStore = await cookies();
  const adminCookie = cookieStore.get(ADMIN_COOKIE_NAME);
  return adminCookie?.value === ADMIN_COOKIE_VALUE;
}

export type AdminResult = {
  error?: string;
  success?: boolean;
};

/**
 * Gate a mutating admin action. Returns an error `AdminResult` when the caller
 * is not an authenticated admin, or `null` when the action may proceed.
 */
async function requireAdmin(): Promise<AdminResult | null> {
  if (!(await isAdminAuthenticated())) {
    return { error: "Unauthorized" };
  }
  return null;
}

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

  const unauthorized = await requireAdmin();
  if (unauthorized) return unauthorized;

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

const wizardAccessSchema = z.object({
  userId: z.string().uuid("Invalid user ID."),
  value: z.boolean(),
});

/**
 * Grant or revoke a single user's Solution Wizard beta access (the per-user
 * `wizard_access` flag). Admin-only; independent of the general approval status.
 */
export async function setWizardAccess(
  userId: string,
  value: boolean,
): Promise<AdminResult> {
  const result = wizardAccessSchema.safeParse({ userId, value });
  if (!result.success) {
    return { error: result.error.issues[0].message };
  }

  const unauthorized = await requireAdmin();
  if (unauthorized) return unauthorized;

  const supabase = createServiceClient();

  const { error } = await supabase
    .from("access_requests")
    .update({ wizard_access: result.data.value })
    .eq("user_id", result.data.userId);

  if (error) {
    console.error("Failed to update wizard access:", error);
    return { error: "Failed to update wizard access." };
  }

  return { success: true };
}

const resetUsageSchema = z.object({
  userId: z.string().uuid("Invalid user ID."),
});

/** Reset a single user's Report Writer counter (count + tokens). Admin-only. */
export async function resetReportUsage(userId: string): Promise<AdminResult> {
  const result = resetUsageSchema.safeParse({ userId });
  if (!result.success) {
    return { error: result.error.issues[0].message };
  }

  const unauthorized = await requireAdmin();
  if (unauthorized) return unauthorized;

  const supabase = createServiceClient();
  const { error } = await supabase
    .from("access_requests")
    .update({ reports_count: 0, report_tokens_used: 0 })
    .eq("user_id", result.data.userId);

  if (error) {
    console.error("Failed to reset report usage:", error);
    return { error: "Failed to reset usage." };
  }

  return { success: true };
}

/** Expose the configured per-user report cap to the (client) admin dashboard. */
export async function getReportWriterMaxReports(): Promise<number> {
  return getReportWriterLimits().maxReports;
}

const limitOverrideSchema = z.object({
  userId: z.string().uuid("Invalid user ID."),
  // null = use the global default; a number sets this user's cap.
  // 1000000 is the UI's "Unlimited" sentinel.
  value: z.number().int().min(0).max(1_000_000).nullable(),
});

/**
 * Set (or clear) a single user's Report Writer cap override. `null` reverts the
 * user to the global `REPORT_WRITER_MAX_REPORTS` default. Admin-only. Used to
 * give demo/team accounts a high or unlimited allowance.
 */
export async function setReportLimitOverride(
  userId: string,
  value: number | null,
): Promise<AdminResult> {
  const result = limitOverrideSchema.safeParse({ userId, value });
  if (!result.success) {
    return { error: result.error.issues[0].message };
  }

  const unauthorized = await requireAdmin();
  if (unauthorized) return unauthorized;

  const supabase = createServiceClient();
  const { error } = await supabase
    .from("access_requests")
    .update({ report_limit_override: result.data.value })
    .eq("user_id", result.data.userId);

  if (error) {
    console.error("Failed to set report limit override:", error);
    return { error: "Failed to set limit." };
  }

  return { success: true };
}
