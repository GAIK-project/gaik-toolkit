import { createServerClient as createSsrServerClient } from "@supabase/ssr";
import { createClient } from "@supabase/supabase-js";
import { cookies } from "next/headers";
import type { CookieToSet } from "./constants";

export async function createServerClient() {
  const cookieStore = await cookies();

  return createSsrServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
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
            // Server Component context - cookies cannot be set, this is expected behavior
          }
        },
      },
    },
  );
}

/**
 * Create a Supabase client without cookies for use inside "use cache" functions.
 * This client uses the anon key and does not require request context.
 * Use this for read-only public data that can be cached.
 */
export function createCacheableClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
  );
}

/**
 * Create a Supabase client with service role key for admin operations.
 * This bypasses RLS and should only be used for trusted server-side operations.
 */
export function createServiceClient() {
  const serviceRoleKey = process.env.SUPABASE_SECRET_KEY;
  if (!serviceRoleKey) {
    throw new Error("SUPABASE_SECRET_KEY is not set");
  }

  return createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, serviceRoleKey, {
    auth: {
      autoRefreshToken: false,
      persistSession: false,
    },
  });
}
