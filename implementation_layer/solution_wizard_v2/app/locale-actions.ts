"use server";

import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";
import { LOCALE_COOKIE, LOCALES, type Locale } from "@/lib/i18n";

export async function setLocale(formData: FormData) {
  const locale = formData.get("locale") as string;
  if (LOCALES.includes(locale as Locale)) {
    const c = await cookies();
    c.set(LOCALE_COOKIE, locale, { path: "/", sameSite: "lax" });
  }
  // Refresh the whole layout so all pages render in the new language.
  revalidatePath("/", "layout");
}
