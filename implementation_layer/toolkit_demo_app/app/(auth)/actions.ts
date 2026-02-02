"use server";

import { redirect } from "next/navigation";
import { z } from "zod";
import { createClient, createServiceClient } from "@/lib/supabase/server";

export type AuthResult = {
  error?: string;
  success?: boolean;
};

const signUpSchema = z.object({
  email: z.email("Please enter a valid email address."),
  password: z.string().min(6, "Password must be at least 6 characters."),
  name: z.string().min(1, "Please enter your full name."),
  company: z.string().optional(),
  useCase: z.string().optional(),
});

const signInSchema = z.object({
  email: z.email("Please enter a valid email address."),
  password: z.string().min(1, "Please enter your password."),
});

export async function signUp(
  _prevState: AuthResult,
  formData: FormData,
): Promise<AuthResult> {
  const rawData = {
    email: formData.get("email"),
    password: formData.get("password"),
    name: formData.get("name"),
    company: formData.get("company") || undefined,
    useCase: formData.get("useCase") || undefined,
  };

  const result = signUpSchema.safeParse(rawData);
  if (!result.success) {
    return { error: result.error.issues[0].message };
  }

  const { email, password, name: fullName, company, useCase } = result.data;

  const supabase = await createClient();

  const { data: authData, error: authError } = await supabase.auth.signUp({
    email,
    password,
    options: {
      data: { full_name: fullName },
    },
  });

  if (authError) {
    if (authError.message.includes("already registered")) {
      return { error: "This email is already registered. Please sign in." };
    }
    return { error: authError.message };
  }

  if (!authData.user) {
    return { error: "Failed to create account. Please try again." };
  }

  // Create access request using service client (bypasses RLS)
  const serviceClient = createServiceClient();
  const { error: requestError } = await serviceClient
    .from("access_requests")
    .insert({
      user_id: authData.user.id,
      email,
      full_name: fullName,
      company,
      use_case: useCase,
      status: "pending",
    });

  if (requestError) {
    console.error("Failed to create access request:", requestError);
    // Don't fail the signup - user was created, just log the error
  }

  redirect("/access-pending");
}

export async function signIn(
  _prevState: AuthResult,
  formData: FormData,
): Promise<AuthResult> {
  const rawData = {
    email: formData.get("email"),
    password: formData.get("password"),
  };

  const result = signInSchema.safeParse(rawData);
  if (!result.success) {
    return { error: result.error.issues[0].message };
  }

  const { email, password } = result.data;

  const supabase = await createClient();

  const { data, error } = await supabase.auth.signInWithPassword({
    email,
    password,
  });

  if (error) {
    return { error: "Invalid email or password." };
  }

  if (!data.user) {
    return { error: "Sign in failed. Please try again." };
  }

  // Check access request status
  const { data: accessRequest } = await supabase
    .from("access_requests")
    .select("status")
    .eq("user_id", data.user.id)
    .single();

  if (!accessRequest) {
    // No access request found - redirect to pending (shouldn't happen normally)
    redirect("/access-pending");
  }

  if (accessRequest.status === "pending") {
    redirect("/access-pending");
  }

  if (accessRequest.status === "rejected") {
    await supabase.auth.signOut();
    return { error: "Your access request was not approved." };
  }

  // Access approved - redirect to home
  redirect("/");
}

export async function signOut(): Promise<void> {
  const supabase = await createClient();
  await supabase.auth.signOut();
  redirect("/sign-in");
}
