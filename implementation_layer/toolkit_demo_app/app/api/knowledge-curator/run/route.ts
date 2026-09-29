import { NextRequest, NextResponse } from "next/server";
import { checkCurateForm } from "@/lib/knowledge-curator/workspace";
import {
  forwardReportRun,
  gateReportWriter,
  recordReportUsage,
} from "@/lib/report-writer/gate";
import { getReportWriterLimits } from "@/lib/report-writer/limits";
import { REPORT_REQUEST_MAX_BYTES } from "@/lib/report-writer/upload-limit";

/**
 * Knowledge Curator run. Carved out of the generic proxy like the Report Writer
 * routes: it passes the same sign-in, approval and rate gate, bounds the run size
 * with the Report Writer limits, and records the curator's tokens. A run is not
 * counted as a report. Quote verification needs no model and goes through the
 * generic proxy (/api/knowledge-curator/verify), which also requires sign-in.
 */
export async function POST(request: NextRequest) {
  const limits = getReportWriterLimits();
  const gate = await gateReportWriter(request, limits.maxReports);
  if (gate instanceof Response) return gate;
  const { userId } = gate;

  const declaredBytes = Number(request.headers.get("content-length") ?? 0);
  if (declaredBytes > REPORT_REQUEST_MAX_BYTES) {
    return NextResponse.json(
      { error: `Uploads exceed the ${limits.maxUploadMb} MB limit.` },
      { status: 413 },
    );
  }

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return NextResponse.json({ error: "Invalid form data." }, { status: 400 });
  }
  const invalid = await checkCurateForm(form, limits);
  if (invalid) {
    return NextResponse.json({ error: invalid.error }, { status: invalid.status });
  }

  // Rebuild FormData for forwarding. The artifacts stay a file part: the backend caps
  // plain form fields at 1 MB, and the normalized texts are larger.
  const fwd = new FormData();
  fwd.append("request", form.get("request") as string);
  fwd.append("artifacts", form.get("artifacts") as File, "artifacts.json");

  return forwardReportRun("/knowledge-curator/run", fwd, async (usage) => {
    if (!userId || !usage.sawResult || !usage.totalTokens) return;
    try {
      await recordReportUsage(userId, 0, usage.totalTokens);
    } catch (e) {
      console.error("[knowledge-curator] failed to record usage:", e);
    }
  });
}
