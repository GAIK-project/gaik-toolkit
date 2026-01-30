import { getGithubPreviewSafe } from "@/lib/link-previews";
import { createClient } from "@/lib/supabase/server";
import { SiteNav } from "./site-nav";

export async function SiteNavServer() {
  const githubPreview = await getGithubPreviewSafe();

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

  return <SiteNav githubPreview={githubPreview} isLoggedIn={isLoggedIn} />;
}
