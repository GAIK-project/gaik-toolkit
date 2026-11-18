// Undo of the last write to the blueprint, from the workspace: wizard_api goes
// back to the version before it, as a new version. The body names the version
// the workspace shows (`{base_version}`). Owner check, a 64 KB bound and the
// refusals (409 nothing_to_undo, cannot_undo, changed_elsewhere, agent_busy)
// passed on through lib/safe-error. Without wizard_api: 503 needs_wizard_api.

import { NextRequest } from "next/server";
import { requireOwnedSession } from "@/lib/session-access";
import { withLogging } from "@/lib/with-logging";
import { audit } from "@/lib/audit";
import { setContextUserId } from "@/lib/request-context";
import { MAX_EDIT_BODY_BYTES } from "@/lib/blueprint-ops";
import { NO_STORE, needsWizardApi, publicSession, readLimitedJson, relayUpstream } from "@/lib/blueprint-proxy";
import { apiUndoBlueprint, wizardApiEnabled } from "@/lib/wizard-api-client";

export const dynamic = "force-dynamic";

export const POST = withLogging(
  "blueprint.undo",
  async (req: NextRequest, { params }: { params: Promise<{ id: string }> }) => {
    const { id } = await params;
    const owned = await requireOwnedSession(id);
    if (!owned) return new Response("Session not found", { status: 404 });
    setContextUserId(owned.user.email);
    if (!wizardApiEnabled()) return needsWizardApi();

    const read = await readLimitedJson(req, MAX_EDIT_BODY_BYTES);
    if ("refused" in read) return read.refused;

    return relayUpstream(
      () => apiUndoBlueprint(id, read.body),
      (body) => Response.json(publicSession(body), { headers: NO_STORE }),
      {
        event: "blueprint.undo",
        sessionId: id,
        onDone: (outcome) =>
          audit("blueprint.ops", {
            actor: owned.user.email,
            resource: { type: "session", id },
            action: "undo",
            outcome,
          }),
      },
    );
  },
);
