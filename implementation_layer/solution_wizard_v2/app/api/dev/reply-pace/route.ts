// Dev/test only: how fast the scripted chat reply is written.
//
// The scripted reply of the mock store is a sentence at 45 ms a word: gone
// before a spec can press Stop. A spec that stops a reply asks for a slower
// pace here; resetting the mock store puts the usual one back. Same DEV_AUTH
// gate as reset-mocks and set-step.

import { NextRequest } from "next/server";
import { DEV_AUTH } from "@/lib/auth";
import { wizardApiEnabled } from "@/lib/wizard-api-client";
import { setMockReplyPace } from "@/lib/mock-sessions";
import { withLogging } from "@/lib/with-logging";

export const dynamic = "force-dynamic";

export const POST = withLogging("dev.reply-pace", async (req: NextRequest) => {
  // These routes need no sign-in, so they exist only for the in-memory mock
  // store that E2E runs use; a stack with a real wizard_api has none of them.
  if (!DEV_AUTH || wizardApiEnabled()) {
    return new Response("Forbidden", { status: 403 });
  }
  const body = (await req.json().catch(() => null)) as { ms?: unknown } | null;
  if (typeof body?.ms !== "number" || !Number.isFinite(body.ms)) {
    return new Response("ms is required", { status: 400 });
  }
  setMockReplyPace(body.ms);
  return Response.json({ ok: true });
});
