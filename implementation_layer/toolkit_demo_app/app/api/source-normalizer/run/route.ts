import { NextRequest, NextResponse } from "next/server";
import {
  forwardReportRun,
  gateReportWriter,
  recordReportUsage,
} from "@/lib/report-writer/gate";
import { getReportWriterLimits } from "@/lib/report-writer/limits";
import {
  COMPRESS_HINT,
  REPORT_REQUEST_MAX_BYTES,
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
  const gate = await gateReportWriter(request, limits.maxReports);
  if (gate instanceof Response) return gate;
  const { userId } = gate;

  // A body over the proxy cap arrives truncated and fails to parse, so reject it
  // by its declared length first.
  const declaredBytes = Number(request.headers.get("content-length") ?? 0);
  if (declaredBytes > REPORT_REQUEST_MAX_BYTES) {
    return NextResponse.json(
      {
        error: `Uploads exceed the ${limits.maxUploadMb} MB limit. ${COMPRESS_HINT}`,
      },
      { status: 413 },
    );
  }

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return NextResponse.json({ error: "Invalid form data." }, { status: 400 });
  }
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

  return forwardReportRun("/source-normalizer/run", fwd, async (usage) => {
    if (!userId || !usage.sawResult || !usage.totalTokens) return;
    try {
      await recordReportUsage(userId, 0, usage.totalTokens);
    } catch (e) {
      console.error("[source-normalizer] failed to record usage:", e);
    }
  });
}
