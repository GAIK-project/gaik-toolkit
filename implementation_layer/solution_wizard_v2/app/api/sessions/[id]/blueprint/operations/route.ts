// Typed operations on the session's full blueprint draft, from the workspace's
// diagram (lib/blueprint-ops). wizard_api applies them all or none and keeps
// the result as a new version; this route checks the owner, bounds the body
// at 64 KB and passes a refusal on only as a known code (lib/safe-error).
// Without wizard_api there is no full draft: 503 needs_wizard_api.

import { NextRequest } from "next/server";
import { requireOwnedSession } from "@/lib/session-access";
import { withLogging } from "@/lib/with-logging";
import { audit } from "@/lib/audit";
import { setContextUserId } from "@/lib/request-context";
import { MAX_EDIT_BODY_BYTES } from "@/lib/blueprint-ops";
import { editResult, needsWizardApi, readLimitedJson, relayUpstream } from "@/lib/blueprint-proxy";
import { apiPostOperations, wizardApiEnabled } from "@/lib/wizard-api-client";

export const dynamic = "force-dynamic";

function operationCount(body: unknown): number {
  const ops = body && typeof body === "object" ? (body as { operations?: unknown }).operations : undefined;
  return Array.isArray(ops) ? ops.length : 0;
}

export const POST = withLogging(
  "blueprint.operations",
  async (req: NextRequest, { params }: { params: Promise<{ id: string }> }) => {
    const { id } = await params;
    const owned = await requireOwnedSession(id);
    if (!owned) return new Response("Session not found", { status: 404 });
    setContextUserId(owned.user.email);
    if (!wizardApiEnabled()) return needsWizardApi();

    const read = await readLimitedJson(req, MAX_EDIT_BODY_BYTES);
    if ("refused" in read) return read.refused;

    return relayUpstream(() => apiPostOperations(id, read.body), editResult, {
      event: "blueprint.operations",
      sessionId: id,
      // How many operations, not what they carry: a name or a description is the user's text.
      onDone: (outcome) =>
        audit("blueprint.ops", {
          actor: owned.user.email,
          resource: { type: "session", id },
          outcome,
          operationCount: operationCount(read.body),
        }),
    });
  },
);
