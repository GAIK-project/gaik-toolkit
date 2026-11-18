// The session's full blueprint draft, read and saved whole. GET answers
// `{version, draft, readonly_sections, draft_digest}`; PUT takes
// `{base_version, base_digest, draft}` (`base_digest`: the `draft_digest` the
// draft was read with) and answers as an edit of operations does. The body may
// be as large as a blueprint, not the 64 KB of an edit: wizard_api counts the
// blueprint's characters (MAX_BLUEPRINT_CHARS), this route only caps the bytes,
// at the most those characters take in UTF-8. Owner check,
// refusals through lib/safe-error; without wizard_api: 503 needs_wizard_api.

import { NextRequest } from "next/server";
import { requireOwnedSession } from "@/lib/session-access";
import { withLogging } from "@/lib/with-logging";
import { audit } from "@/lib/audit";
import { setContextUserId } from "@/lib/request-context";
import { MAX_BLUEPRINT_CHARS } from "@/lib/blueprint-ops";
import { editResult, needsWizardApi, passJson, readLimitedJson, relayUpstream } from "@/lib/blueprint-proxy";
import { apiGetFullBlueprint, apiPutFullBlueprint, wizardApiEnabled } from "@/lib/wizard-api-client";

export const dynamic = "force-dynamic";

/** A blueprint as JSON at 4 bytes a character (UTF-8's most), and the
 * `{base_version, base_digest, draft}` around it. */
const MAX_BODY_BYTES = 4 * MAX_BLUEPRINT_CHARS + 1024;

export const GET = withLogging(
  "blueprint.full.read",
  async (_req: NextRequest, { params }: { params: Promise<{ id: string }> }) => {
    const { id } = await params;
    const owned = await requireOwnedSession(id);
    if (!owned) return new Response("Session not found", { status: 404 });
    setContextUserId(owned.user.email);
    if (!wizardApiEnabled()) return needsWizardApi();

    return relayUpstream(() => apiGetFullBlueprint(id), passJson, {
      event: "blueprint.full.read",
      sessionId: id,
    });
  },
);

export const PUT = withLogging(
  "blueprint.full.save",
  async (req: NextRequest, { params }: { params: Promise<{ id: string }> }) => {
    const { id } = await params;
    const owned = await requireOwnedSession(id);
    if (!owned) return new Response("Session not found", { status: 404 });
    setContextUserId(owned.user.email);
    if (!wizardApiEnabled()) return needsWizardApi();

    const read = await readLimitedJson(req, MAX_BODY_BYTES);
    if ("refused" in read) return read.refused;

    return relayUpstream(() => apiPutFullBlueprint(id, read.body), editResult, {
      event: "blueprint.full.save",
      sessionId: id,
      onDone: (outcome) =>
        audit("blueprint.update", {
          actor: owned.user.email,
          resource: { type: "session", id },
          action: "full",
          outcome,
        }),
    });
  },
);
