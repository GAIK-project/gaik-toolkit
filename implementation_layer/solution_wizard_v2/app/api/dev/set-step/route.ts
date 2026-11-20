// Dev/test only: move a mock session to a given step.
//
// Gathering (steps 1-3) has no UI affordance to advance — the agent moves the
// session on. E2E specs running against the mock store therefore cannot click
// their way to a later phase, so they say where they want to be instead. Same dev-login gate as reset-mocks.

import { NextRequest } from "next/server";
import { proxyAuthEnabled } from "@/lib/proxy-auth";
import { devAuthActive } from "@/lib/supabase-auth";
import { wizardApiEnabled } from "@/lib/wizard-api-client";
import { rejectGate, setSessionStep } from "@/lib/mock-sessions";
import { withLogging } from "@/lib/with-logging";

export const dynamic = "force-dynamic";

export const POST = withLogging("dev.set-step", async (req: NextRequest) => {
  // These routes need no sign-in, so they exist only for the in-memory mock
  // store that E2E runs use; a stack with a real wizard_api has none of them.
  // Only where the dev login is the one in use, not behind another sign-in.
  if (!devAuthActive() || proxyAuthEnabled() || wizardApiEnabled()) {
    return new Response("Forbidden", { status: 403 });
  }
  const body = (await req.json().catch(() => null)) as {
    id?: string;
    step?: number;
    /** A run id to record as the session's successful test run, or null to clear it. */
    successfulRun?: string | null;
    /** Mark the gate at that step rejected: the page has no reject control of its own. */
    rejected?: boolean;
    /** The digest of the package the successful run tested, as wizard_api keeps it; null clears it. */
    testedPackage?: string | null;
    /** The digest of the package as it is now: the mock has no package to read one from. */
    packageDigest?: string | null;
  } | null;
  if (!body?.id || typeof body.step !== "number") {
    return new Response("id and step are required", { status: 400 });
  }
  const successfulRun =
    typeof body.successfulRun === "string" || body.successfulRun === null ? body.successfulRun : undefined;
  const digest = (value: unknown) => (typeof value === "string" || value === null ? value : undefined);
  const session = setSessionStep(body.id, body.step, successfulRun, {
    testedPackage: digest(body.testedPackage),
    packageDigest: digest(body.packageDigest),
  });
  if (!session) {
    return new Response("Session not found", { status: 404 });
  }
  if (body.rejected === true) rejectGate(body.id);
  return Response.json({ id: session.id, step: session.step });
});
