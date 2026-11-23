// Sample input for a sandbox run (#95): the files a PoC reads from
// poc/sample_input/. GET lists them, POST adds one. wizard_api owns the rules
// (only that directory, name checks, 50 MB); this route relays its answers so a
// refused file is explained in the api's words. Empty list in mock mode.

import { NextRequest } from "next/server";
import { requireOwnedSession } from "@/lib/session-access";
import { withLogging } from "@/lib/with-logging";
import { audit } from "@/lib/audit";
import { logger } from "@/lib/logger";
import { getTraceId, setContextUserId } from "@/lib/request-context";
import { wizardApiEnabled, apiListPocInputs, apiUploadPocInput } from "@/lib/wizard-api-client";
import { declaredLengthProblem, fileSizeProblem } from "@/lib/upload-limits";
import { isCrossSiteWrite } from "@/lib/same-origin";
import { relayError, unreachableResponse } from "@/lib/safe-error";

export const dynamic = "force-dynamic";

// wizard_api refuses larger files (poc_service.MAX_INPUT_BYTES); checked here
// too, before the body is read, so a 60 MB upload is not held in memory only
// to be refused. The limits live in lib/upload-limits, shared with the cases relay.

export const GET = withLogging(
  "poc.input.list",
  async (_req: NextRequest, { params }: { params: Promise<{ id: string }> }) => {
    const { id } = await params;
    const owned = await requireOwnedSession(id);
    if (!owned) {
      return new Response("Session not found", { status: 404 });
    }
    setContextUserId(owned.user.email);

    if (!wizardApiEnabled()) {
      return Response.json({ files: [] });
    }
    try {
      return Response.json(await apiListPocInputs(id));
    } catch (err) {
      logger.error({ traceId: getTraceId(), err, sessionId: id }, "poc.input.list failed");
      return Response.json({ files: [] });
    }
  },
);

export const POST = withLogging(
  "poc.input.upload",
  async (req: NextRequest, { params }: { params: Promise<{ id: string }> }) => {
    // The proxy does not see this route (see its matcher), so the
    // cross-site check it does for every other write happens here.
    if (isCrossSiteWrite(req)) return new Response("Cross-site request refused", { status: 403 });
    const { id } = await params;
    const owned = await requireOwnedSession(id);
    if (!owned) {
      return new Response("Session not found", { status: 404 });
    }
    setContextUserId(owned.user.email);

    if (!wizardApiEnabled()) {
      return Response.json({ detail: "PoC input is not available" }, { status: 404 });
    }

    // Settled before the body is read, since formData() buffers it whole (#297).
    const declared = declaredLengthProblem(req.headers.get("content-length"));
    if (declared) return Response.json({ detail: declared.detail }, { status: declared.status });
    let file: File | null = null;
    try {
      const form = await req.formData();
      const entry = form.get("file");
      file = entry instanceof File ? entry : null;
    } catch {
      file = null;
    }
    if (!file) {
      return Response.json({ detail: "send one file in the 'file' field" }, { status: 400 });
    }
    const size = fileSizeProblem(file.size);
    if (size) return Response.json({ detail: size.detail }, { status: size.status });

    try {
      const upstreamForm = new FormData();
      upstreamForm.append("file", file, file.name);
      const upstream = await apiUploadPocInput(id, upstreamForm);
      // The api's 409/413/422 say which rule the file broke; only those pass.
      if (!upstream.ok) return relayError(upstream);
      const body = await upstream.json().catch(() => ({}));
      audit("poc.input.upload", {
        actor: owned.user.email,
        resource: { type: "session", id },
        outcome: "success",
        action: `${file.name} (${file.size} B)`,
      });
      // 201 with the stored name.
      return Response.json(body, { status: upstream.status });
    } catch (err) {
      logger.error({ traceId: getTraceId(), err, sessionId: id }, "poc.input.upload failed");
      return unreachableResponse();
    }
  },
);
