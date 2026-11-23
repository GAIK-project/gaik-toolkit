import { NextRequest } from "next/server";
import { BPMN_VISUAL_STEP, hasBpmnSpike } from "@/lib/bpmn-spike";
import { BLUEPRINT_CHANGED_ELSEWHERE, baseIsStale } from "@/lib/blueprint-draft";
import { syncSessionBpmn } from "@/lib/bpmn-generate";
import { BPMN_XML_MAX_BYTES, BpmnLintBusyError, lintBpmnXml } from "@/lib/bpmn-lint";
import { requireOwnedSession } from "@/lib/session-access";
import { declaredLengthProblem } from "@/lib/upload-limits";
import { saveBlueprintAfterBpmnSync } from "@/lib/sessions";
import { wizardApiEnabled } from "@/lib/wizard-api-client";
import { withLogging } from "@/lib/with-logging";
import { audit } from "@/lib/audit";
import { logger } from "@/lib/logger";
import { getTraceId, setContextUserId } from "@/lib/request-context";

export const dynamic = "force-dynamic";

export const POST = withLogging(
  "bpmn.sync",
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
    if (!hasBpmnSpike(id) || owned.session.step < BPMN_VISUAL_STEP) {
      return new Response("BPMN not available for this session", { status: 404 });
    }

    // Size is checked before the body is parsed and again after: the linter
    // and the generator are child processes, and a document far larger than
    // any real diagram is not a diagram, it is load (review T3).
    // A request that does not say its length (a chunked body) would be
    // buffered whole by req.json() before any check, so it is refused too.
    const declared = declaredLengthProblem(
      req.headers.get("content-length"),
      BPMN_XML_MAX_BYTES * 1.5,
      0,
    );
    if (declared?.status === 411) {
      return new Response("send the BPMN document with a content-length", { status: 411 });
    }
    if (declared) {
      return new Response(`BPMN document too large (max ${BPMN_XML_MAX_BYTES} bytes)`, {
        status: 413,
      });
    }

    let body: { xml?: string; force?: boolean; base?: unknown };
    try {
      body = await req.json();
    } catch {
      return new Response("Invalid JSON", { status: 400 });
    }
    if (!body.xml?.trim()) {
      return new Response("Missing xml", { status: 400 });
    }
    // A save that started by itself names the blueprint the canvas was drawn
    // from: merged into a newer one the agent wrote, the canvas would drop the
    // steps it never showed.
    if (baseIsStale(body.base, owned.session.blueprint)) {
      return Response.json({ error: BLUEPRINT_CHANGED_ELSEWHERE }, { status: 409 });
    }
    if (Buffer.byteLength(body.xml, "utf8") > BPMN_XML_MAX_BYTES) {
      return new Response(`BPMN document too large (max ${BPMN_XML_MAX_BYTES} bytes)`, {
        status: 413,
      });
    }

    // The linter runs as a child process. If it cannot start at all — e.g. a
    // dependency missing from the standalone build — that is an infrastructure
    // failure, not a rejected diagram, so it must not block a save: linting is
    // quality assurance, not a persistence gate. Log it and proceed with
    // lint === null (the response reports the diagram was not linted). A lint
    // that RAN and found blocking errors is still enforced below (#47).
    let lint: Awaited<ReturnType<typeof lintBpmnXml>> | null = null;
    try {
      lint = await lintBpmnXml(body.xml);
    } catch (err) {
      // Busy is not "the linter cannot run": saving unlinted would let a burst
      // of requests skip the lint, so this one is refused and retried instead.
      if (err instanceof BpmnLintBusyError) {
        return new Response("BPMN validation is busy, try again shortly", {
          status: 503,
          headers: { "Retry-After": "2" },
        });
      }
      logger.warn(
        { traceId: getTraceId(), err, sessionId: id },
        "bpmn.sync lint unavailable, proceeding without it",
      );
    }

    // Blocking errors prevent silent persist (#47). Callers may pass force=true
    // only for emergency recovery — not exposed in the normal UI. A null lint
    // means the linter could not run, which does not gate the save.
    if (lint && !lint.ok && !body.force) {
      audit("bpmn.sync", {
        actor: owned.user.email,
        resource: { type: "session", id },
        outcome: "denied",
        reason: "lint_failed",
      });
      return Response.json(
        {
          error: "bpmn_lint_failed",
          message: "BPMN validation failed",
          lint,
        },
        { status: 422 },
      );
    }

    try {
      const result = await syncSessionBpmn(id, owned.session.blueprint, body.xml);
      // wizard_api's /bpmn/sync stores the version itself; saving again here
      // wrote a second, identical one on every diagram save. Only the mock
      // sync leaves the save to us.
      if (!wizardApiEnabled()) {
        await saveBlueprintAfterBpmnSync(id, result.blueprint);
      }
      audit("bpmn.sync", {
        actor: owned.user.email,
        resource: { type: "session", id },
        outcome: "success",
      });
      return Response.json({
        blueprint: result.blueprint,
        xml: result.xml,
        lint,
      });
    } catch (err) {
      logger.error({ traceId: getTraceId(), err, sessionId: id }, "bpmn.sync failed");
      audit("bpmn.sync", {
        actor: owned.user.email,
        resource: { type: "session", id },
        outcome: "error",
      });
      return new Response("BPMN sync failed", { status: 500 });
    }
  },
);
