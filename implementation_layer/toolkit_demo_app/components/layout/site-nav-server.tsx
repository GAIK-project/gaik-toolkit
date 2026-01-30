import { getGithubPreviewSafe } from "@/lib/link-previews";
import { createClient } from "@/lib/supabase/server";
import { headers } from "next/headers";
import { SiteNav } from "./site-nav";

export async function SiteNavServer() {
  const githubPreview = await getGithubPreviewSafe();

  // Get pathname from proxy header for SSR active state
  const headersList = await headers();
  const pathname = headersList.get("x-current-path") || "/";

  let isLoggedIn = false;
  try {
    const supabase = await createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();
    isLoggedIn = !!user;
  } catch {
    // ignore auth errors
  }

  return <SiteNav pathname={pathname} githubPreview={githubPreview} isLoggedIn={isLoggedIn} />;
}
