import { NextRequest, NextResponse } from "next/server";
import {
  bodyLimitFor,
  declaresMoreThan,
  readFormWithin,
} from "@/lib/upload-limits";
import {
  forwardReportRun,
  gateReportWriter,
  recordReportUsage,
} from "@/lib/report-writer/gate";
import { getReportWriterLimits } from "@/lib/report-writer/limits";
import {
  COMPRESS_HINT,
} from "@/lib/report-writer/upload-limit";
import { checkNormalizeForm } from "@/lib/source-normalizer/workspace";

/**
 * Source Normalizer run. Carved out of the generic proxy like the Report Writer
 * routes: it passes the same sign-in, approval and rate gate, shares the upload
 * limit, and records the tokens of the transcription and image calls. A run is
 * not counted as a report.
 */
export async function POST(request: NextRequest) {
  const limits = getReportWriterLimits();
  const bodyLimit = bodyLimitFor("/source-normalizer/run");
  const tooLarge = () =>
    NextResponse.json(
      { error: `Uploads exceed the ${limits.maxUploadMb} MB limit. ${COMPRESS_HINT}` },
      { status: 413 },
    );
  // A body that declares more than the run takes is refused before the gate
  // below takes a trial run. A body sent without a Content-Length is measured
  // only after the gate, so its body is not parsed before sign-in.
  if (declaresMoreThan(request, bodyLimit.maxBytes)) {
    await request.body?.cancel().catch(() => {});
    return tooLarge();
  }

  const gate = await gateReportWriter(request, limits.maxReports);
  if (gate instanceof Response) return gate;
  const { userId, staff } = gate;

  // Parse the multipart body within the route's limits (lib/upload-limits.ts):
  // this copy stops at the first chunk past the size, and a form with more files
  // than the run takes is refused. Next.js has already buffered the request (up
  // to proxyClientMaxBodySize), so this bounds what is parsed, not what arrived.
  const read = await readFormWithin(request, bodyLimit);
  if (!read.ok) {
    if (read.status === 413) return tooLarge();
    return NextResponse.json({ error: read.error }, { status: 400 });
  }
  const form = read.form;
  const invalid = checkNormalizeForm(form, limits);
  if (invalid) {
    const hint = invalid.status === 413 ? ` ${COMPRESS_HINT}` : "";
    return NextResponse.json(
      { error: invalid.error + hint },
      { status: invalid.status },
    );
  }

  // Rebuild FormData (buffered Files) for forwarding, like the Report Writer routes.
  const fwd = new FormData();
  fwd.append("manifest", form.get("manifest") as string);
  for (const f of form.getAll("files") as File[]) fwd.append("files", f, f.name);

  return forwardReportRun("/source-normalizer/run", fwd, staff, async (usage) => {
    if (!userId || !usage.sawResult || !usage.totalTokens) return;
    try {
      await recordReportUsage(userId, 0, usage.totalTokens);
    } catch (e) {
      console.error("[source-normalizer] failed to record usage:", e);
    }
  }, userId);
}
