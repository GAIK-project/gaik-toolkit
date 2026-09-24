"use server";

import { revalidatePath } from "next/cache";
import {
  advanceSession,
  regressSession,
  approveGate,
} from "@/lib/mock-sessions";

function refresh(id: string) {
  revalidatePath(`/sessions/${id}`);
  revalidatePath("/");
}

export async function advance(formData: FormData) {
  const id = formData.get("id") as string;
  advanceSession(id);
  refresh(id);
}

export async function regress(formData: FormData) {
  const id = formData.get("id") as string;
  regressSession(id);
  refresh(id);
}

export async function approve(formData: FormData) {
  const id = formData.get("id") as string;
  approveGate(id);
  refresh(id);
}
