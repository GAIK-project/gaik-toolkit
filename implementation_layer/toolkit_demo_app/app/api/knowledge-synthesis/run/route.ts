import { NextRequest, NextResponse } from "next/server";
import { checkSynthesizeForm } from "@/lib/knowledge-synthesis/workspace";
import {
  forwardReportRun,
  gateReportWriter,
  recordReportUsage,
} from "@/lib/report-writer/gate";
import { getReportWriterLimits } from "@/lib/report-writer/limits";
import { REPORT_REQUEST_MAX_BYTES } from "@/lib/report-writer/upload-limit";

/**
 * Knowledge Synthesis run. Carved out of the generic proxy like the Report Writer routes:
 * it passes the same sign-in, approval, quota and rate gate and bounds the run size with
 * the Report Writer limits. The synthesis is the costly stage (a writer call and a reviewer
 * call per section), so a successful run counts as one report and its tokens are recorded.
 * Rebuilding the report from edited sections needs no model and goes through the generic
 * proxy (/api/knowledge-synthesis/rebuild), which also requires sign-in.
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
  const invalid = await checkSynthesizeForm(form, limits);
  if (invalid) {
    return NextResponse.json({ error: invalid.error }, { status: invalid.status });
  }

  // Rebuild FormData for forwarding. The artifacts stay a file part: the backend caps plain
  // form fields at 1 MB, and the knowledge is larger.
  const fwd = new FormData();
  fwd.append("request", form.get("request") as string);
  fwd.append("artifacts", form.get("artifacts") as File, "artifacts.json");
  const sample = form.get("sample_report");
  if (sample instanceof File) fwd.append("sample_report", sample, sample.name);

  return forwardReportRun("/knowledge-synthesis/run", fwd, async (usage) => {
    if (!userId || !usage.sawResult) return;
    try {
      await recordReportUsage(userId, 1, usage.totalTokens);
    } catch (e) {
      console.error("[knowledge-synthesis] failed to record usage:", e);
    }
  });
}
