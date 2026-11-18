// One file of the PoC package for the PoC tab's editor: read as text, saved
// over the file it was read from. wizard_api decides what may be opened and
// changed (only the session's own text files under poc/, never an environment
// file with keys); this route checks the owner, bounds the body and passes a
// refusal on only as a known code (lib/safe-error). Without wizard_api the
// mock store answers, so the editor can be tried and tested.

import { NextRequest } from "next/server";
import { requireOwnedSession } from "@/lib/session-access";
import { withLogging } from "@/lib/with-logging";
import { audit } from "@/lib/audit";
import { logger } from "@/lib/logger";
import { getTraceId, setContextUserId } from "@/lib/request-context";
import { currentTraceId, errorResponse, relayError, unreachableResponse } from "@/lib/safe-error";
import { declaredLengthProblem } from "@/lib/upload-limits";
import { MAX_POC_FILE_BYTES } from "@/lib/poc-file";
import { getMockPocFile, putMockPocFile, type MockPocFileError } from "@/lib/mock-sessions";
import { apiGetPocFile, apiPutPocFile, wizardApiEnabled } from "@/lib/wizard-api-client";

export const dynamic = "force-dynamic";

const MAX_PATH_CHARS = 512;
// The text as JSON: every character can be an escape, and the digest and the
// keys ride along.
const MAX_BODY_BYTES = MAX_POC_FILE_BYTES * 6 + 1024;
const NO_STORE = { "Cache-Control": "no-store" };

function refusal(status: number, error: string, message: string, extra: { variables?: string[] } = {}): Response {
  return errorResponse({ error, message, trace_id: currentTraceId(), ...extra }, status);
}

function pathOf(req: NextRequest): string | null {
  const path = req.nextUrl.searchParams.get("path");
  return path && path.length <= MAX_PATH_CHARS ? path : null;
}

function isMockError(value: object): value is MockPocFileError {
  return "status" in value && "error" in value;
}

export const GET = withLogging(
  "poc.file.read",
  async (req: NextRequest, { params }: { params: Promise<{ id: string }> }) => {
    const { id } = await params;
    const owned = await requireOwnedSession(id);
    if (!owned) return new Response("Session not found", { status: 404 });
    setContextUserId(owned.user.email);

    const path = pathOf(req);
    if (!path) return refusal(422, "invalid_path", "the path is not a file of the package");

    if (!wizardApiEnabled()) {
      const file = getMockPocFile(id, path);
      if (isMockError(file)) return refusal(file.status, file.error, file.message);
      return Response.json(file, { headers: NO_STORE });
    }
    let upstream: Response;
    try {
      upstream = await apiGetPocFile(id, path);
    } catch (err) {
      logger.error({ traceId: getTraceId(), err, sessionId: id }, "poc.file.read failed");
      return unreachableResponse();
    }
    if (!upstream.ok) return relayError(upstream);
    return new Response(await upstream.text(), {
      headers: { "Content-Type": "application/json", ...NO_STORE },
    });
  },
);

export const PUT = withLogging(
  "poc.file.save",
  async (req: NextRequest, { params }: { params: Promise<{ id: string }> }) => {
    const { id } = await params;
    const owned = await requireOwnedSession(id);
    if (!owned) return new Response("Session not found", { status: 404 });
    setContextUserId(owned.user.email);

    const path = pathOf(req);
    if (!path) return refusal(422, "invalid_path", "the path is not a file of the package");

    // Before the body is read: one that does not say its length would be
    // buffered whole by req.json().
    const declared = declaredLengthProblem(req.headers.get("content-length"), MAX_BODY_BYTES, 0);
    if (declared?.status === 411) return refusal(411, "length_required", "send the file with a content-length");
    if (declared) return refusal(413, "file_too_large", "the file is too large to save here");

    const body = (await req.json().catch(() => null)) as { content?: unknown; base_digest?: unknown } | null;
    if (!body || typeof body.content !== "string" || typeof body.base_digest !== "string" || !body.base_digest) {
      return refusal(400, "bad_request", "content and base_digest are required");
    }
    if (Buffer.byteLength(body.content, "utf8") > MAX_POC_FILE_BYTES) {
      return refusal(413, "file_too_large", "the file is too large to save here");
    }

    // The file's name and nothing of its content: an edit can carry anything.
    const saved = (outcome: "success" | "error") =>
      audit("poc.file.save", {
        actor: owned.user.email,
        resource: { type: "session", id },
        outcome,
        action: path,
      });

    if (!wizardApiEnabled()) {
      const file = putMockPocFile(id, path, body.content, body.base_digest);
      if (isMockError(file)) {
        saved("error");
        return refusal(file.status, file.error, file.message, file.variables ? { variables: file.variables } : {});
      }
      saved("success");
      return Response.json(file, { headers: NO_STORE });
    }
    let upstream: Response;
    try {
      upstream = await apiPutPocFile(id, path, body.content, body.base_digest);
    } catch (err) {
      logger.error({ traceId: getTraceId(), err, sessionId: id }, "poc.file.save failed");
      return unreachableResponse();
    }
    if (!upstream.ok) {
      saved("error");
      return relayError(upstream);
    }
    saved("success");
    return new Response(await upstream.text(), {
      headers: { "Content-Type": "application/json", ...NO_STORE },
    });
  },
);
