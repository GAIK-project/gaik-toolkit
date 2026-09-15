"use server";

import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/current-user";
import { createSession } from "@/lib/mock-sessions";

export async function startSession(formData: FormData) {
  const user = await getCurrentUser();
  if (!user) redirect("/login");

  const title = (formData.get("title") as string) ?? "";
  const session = createSession(user.email, title);
  redirect(`/sessions/${session.id}`);
}
