import { NextRequest } from "next/server";
import { parseBlueprintJson } from "@/lib/blueprint-parse";
import { BLUEPRINT_CHANGED_ELSEWHERE, baseIsStale } from "@/lib/blueprint-draft";
import { requireOwnedSession } from "@/lib/session-access";
import { patchSessionBlueprint } from "@/lib/sessions";
import { withLogging } from "@/lib/with-logging";
import { audit } from "@/lib/audit";
import { setContextUserId } from "@/lib/request-context";
import { relayErrorBody } from "@/lib/safe-error";
import { WizardApiError } from "@/lib/wizard-api-client";

export const dynamic = "force-dynamic";

export const PATCH = withLogging(
  "blueprint.patch",
  async (
    req: NextRequest,
    { params }: { params: Promise<{ id: string }> },
  ) => {
    const { id } = await params;
    const owned = await requireOwnedSession(id);
    if (!owned) {
      return new Response("Session not found", { status: 404 });
    }
    setContextUserId(owned.user.email);

    let body: { content?: unknown; note?: string; base?: unknown; base_version?: unknown };
    try {
      body = await req.json();
    } catch {
      return new Response("Invalid JSON", { status: 400 });
    }
    // A save that started by itself names the blueprint its edit was made on;
    // one the user chose to send over a newer version names none.
    // `base_version` is the version it was made on: wizard_api checks it again
    // where the save is written, so a version stored in between is caught too.
    const baseVersion = typeof body.base_version === "number" ? body.base_version : undefined;
    if (
      baseIsStale(body.base, owned.session.blueprint) ||
      (baseVersion !== undefined && baseVersion !== owned.session.activeVersion)
    ) {
      return Response.json({ error: BLUEPRINT_CHANGED_ELSEWHERE }, { status: 409 });
    }

    const parsed =
      typeof body.content === "string"
        ? parseBlueprintJson(body.content)
        : parseBlueprintJson(JSON.stringify(body.content ?? {}));
    if (!parsed) {
      return new Response("Invalid blueprint", { status: 400 });
    }

    let updated: Awaited<ReturnType<typeof patchSessionBlueprint>>;
    try {
      updated = await patchSessionBlueprint(
        id,
        parsed,
        typeof body.note === "string" ? body.note : "Blueprint päivitetty JSON-editorista",
        baseVersion,
      );
    } catch (err) {
      // wizard_api refused the save (changed_elsewhere, agent_busy,
      // unsupported_edit): its own words, as lib/safe-error lets them through.
      if (err instanceof WizardApiError) {
        audit("blueprint.update", {
          actor: owned.user.email,
          resource: { type: "session", id },
          outcome: "denied",
          reason: err.code,
        });
        return relayErrorBody(err.status, err.body);
      }
      throw err;
    }
    if (!updated) {
      audit("blueprint.update", {
        actor: owned.user.email,
        resource: { type: "session", id },
        outcome: "error",
      });
      return new Response("Blueprint save failed", { status: 500 });
    }

    audit("blueprint.update", {
      actor: owned.user.email,
      resource: { type: "session", id },
      outcome: "success",
      stepCount: updated.blueprint.steps.length,
    });
    // `version`: what the save wrote, the base of the next save by itself.
    return Response.json({ blueprint: updated.blueprint, version: updated.activeVersion });
  },
);
