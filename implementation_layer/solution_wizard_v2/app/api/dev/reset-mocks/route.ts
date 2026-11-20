import { proxyAuthEnabled } from "@/lib/proxy-auth";
import { devAuthActive } from "@/lib/supabase-auth";
import { wizardApiEnabled } from "@/lib/wizard-api-client";
import { resetMockSessions } from "@/lib/mock-sessions";
import { withLogging } from "@/lib/with-logging";

export const dynamic = "force-dynamic";

export const POST = withLogging("dev.reset-mocks", async () => {
  // These routes need no sign-in, so they exist only for the in-memory mock
  // store that E2E runs use; a stack with a real wizard_api has none of them.
  // Only where the dev login is the one in use, not behind another sign-in.
  if (!devAuthActive() || proxyAuthEnabled() || wizardApiEnabled()) {
    return new Response("Forbidden", { status: 403 });
  }
  resetMockSessions();
  return Response.json({ ok: true });
});
