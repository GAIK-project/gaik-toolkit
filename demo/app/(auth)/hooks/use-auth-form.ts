"use client";

import { useState, type FormEvent } from "react";

export type FormState = "idle" | "submitting" | "done";

export function useAuthForm(delay = 1000) {
  const [status, setStatus] = useState<FormState>("idle");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (status === "submitting") return;
    setStatus("submitting");
    window.setTimeout(() => setStatus("done"), delay);
  }

  const isSubmitting = status === "submitting";
  const isDone = status === "done";

  return { status, isSubmitting, isDone, handleSubmit };
}
