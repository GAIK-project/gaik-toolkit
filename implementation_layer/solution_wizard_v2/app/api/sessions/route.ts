// Creates a session with a given name and no first message.
//
// In the interface a session starts from the user's first message
// (app/actions.ts). A client that needs a session without sending the wizard
// anything (the end-to-end specs, a script) asks for one here. It gives a
// signed-in user nothing more than the start view does: a session of their own.

import { NextRequest } from "next/server";
import { getCurrentUser } from "@/lib/current-user";
import { createSession } from "@/lib/sessions";
import { audit } from "@/lib/audit";
import { getI18n } from "@/lib/i18n";
import { logger } from "@/lib/logger";
import { getTraceId, setContextUserId } from "@/lib/request-context";
import { withLogging } from "@/lib/with-logging";
import { WizardApiError } from "@/lib/wizard-api-client";

export const dynamic = "force-dynamic";

const TITLE_MAX = 255;

export const POST = withLogging("session.create", async (req: NextRequest) => {
  const user = await getCurrentUser();
  if (!user) return Response.json({ error: "unauthenticated" }, { status: 401 });
  setContextUserId(user.email);

  const body = (await req.json().catch(() => null)) as { title?: unknown } | null;
  const given = body?.title;
  if (given !== undefined && typeof given !== "string") {
    return Response.json({ error: "invalid_title" }, { status: 400 });
  }
  const typed = (given ?? "").trim();
  if (typed.length > TITLE_MAX) return Response.json({ error: "invalid_title" }, { status: 400 });
  // A session started without a name gets one in the interface's language.
  const title = typed || (await getI18n()).t.untitledSession;

  try {
    const session = await createSession(user.email, title);
    audit("session.create", {
      actor: user.email,
      resource: { type: "session", id: session.id },
      outcome: "success",
    });
    return Response.json({ id: session.id }, { status: 201 });
  } catch (err) {
    if (err instanceof WizardApiError && err.code === "session_limit") {
      audit("session.create", { actor: user.email, outcome: "denied" });
      return Response.json({ error: "session_limit" }, { status: 429 });
    }
    logger.error({ traceId: getTraceId(), err }, "session.create failed");
    audit("session.create", { actor: user.email, outcome: "error" });
    return Response.json({ error: "failed" }, { status: 502 });
  }
});
