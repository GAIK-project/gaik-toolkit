import { createClient } from "@/lib/supabase/server";

export async function getAccessStatus(): Promise<{
  isLoggedIn: boolean;
  status: "pending" | "approved" | "rejected" | null;
  email: string | null;
}> {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return { isLoggedIn: false, status: null, email: null };
  }

  const { data: accessRequest } = await supabase
    .from("access_requests")
    .select("status")
    .eq("user_id", user.id)
    .single();

  return {
    isLoggedIn: true,
    status: accessRequest?.status || null,
    email: user.email || null,
  };
}
