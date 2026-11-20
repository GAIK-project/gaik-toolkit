import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { cookies } from "next/headers";
import { supabaseSettings } from "@/lib/supabase-auth";

type CookieToSet = { name: string; value: string; options: CookieOptions };

export async function createClient() {
  const settings = supabaseSettings();
  if (!settings) {
    throw new Error(
      "Missing WIZARD_SUPABASE_URL / WIZARD_SUPABASE_KEY. For local UI set NEXT_PUBLIC_DEV_AUTH=true in .env.local (see .env.example).",
    );
  }
  const { url, key } = settings;

  const cookieStore = await cookies();

  return createServerClient(
    url,
    key,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet: CookieToSet[]) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options),
            );
          } catch {
            // setAll was called from a Server Component; the proxy handles the session
            // refresh, so this can be ignored.
          }
        },
      },
    },
  );
}
