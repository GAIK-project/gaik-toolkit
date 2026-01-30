import { createClient } from "@/lib/supabase/server";
import { DemoCards } from "./components/demo-cards";
import { Hero } from "./components/hero";
import { InstallSnippet } from "./components/install-snippet";

export default async function HomePage() {
  const bypassAuth = process.env.BYPASS_AUTH === "true";
  let isUnlocked = bypassAuth;

  if (!bypassAuth) {
    const supabase = await createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();

    if (user) {
      const { data } = await supabase
        .from("access_requests")
        .select("status")
        .eq("user_id", user.id)
        .single();
      isUnlocked = data?.status === "approved";
    }
  }

  return (
    <div className="space-y-24">
      <Hero />
      <DemoCards isUnlocked={isUnlocked} />
      <InstallSnippet />
    </div>
  );
}
