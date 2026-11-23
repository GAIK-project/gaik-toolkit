// Dev/test only: make a mock session start as the live agent's sessions do,
// with no requirement checklist and an empty conversation.
//
// With the live agent the chat is the page while requirements are gathered
// (lib/session-start). The mock store that E2E runs use seeds a checklist and
// an opening question, so a spec asks for that start here. Same dev-login gate
// as reset-mocks and set-step.

import { NextRequest } from "next/server";
import { proxyAuthEnabled } from "@/lib/proxy-auth";
import { devAuthActive } from "@/lib/supabase-auth";
import { wizardApiEnabled } from "@/lib/wizard-api-client";
import { startWithoutChecklist } from "@/lib/mock-sessions";
import { withLogging } from "@/lib/with-logging";

export const dynamic = "force-dynamic";

export const POST = withLogging("dev.live-start", async (req: NextRequest) => {
  // These routes need no sign-in, so they exist only for the in-memory mock
  // store that E2E runs use; a stack with a real wizard_api has none of them.
  // Only where the dev login is the one in use, not behind another sign-in.
  if (!devAuthActive() || proxyAuthEnabled() || wizardApiEnabled()) {
    return new Response("Forbidden", { status: 403 });
  }
  const body = (await req.json().catch(() => null)) as { id?: string } | null;
  if (!body?.id) {
    return new Response("id is required", { status: 400 });
  }
  const session = startWithoutChecklist(body.id);
  if (!session) {
    return new Response("Session not found", { status: 404 });
  }
  return Response.json({ id: session.id, step: session.step });
});
