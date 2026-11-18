import { NextRequest, NextResponse } from "next/server";
import {
  bodyLimitFor,
  declaresMoreThan,
  readFormWithin,
} from "@/lib/upload-limits";
import { checkSynthesizeForm } from "@/lib/knowledge-synthesis/workspace";
import {
  forwardReportRun,
  gateReportWriter,
  recordReportUsage,
} from "@/lib/report-writer/gate";
import { getReportWriterLimits } from "@/lib/report-writer/limits";

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
  const bodyLimit = bodyLimitFor("/knowledge-synthesis/run");
  const tooLarge = () =>
    NextResponse.json(
      { error: `Uploads exceed the ${limits.maxUploadMb} MB limit.` },
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

  return forwardReportRun("/knowledge-synthesis/run", fwd, staff, async (usage) => {
    if (!userId || !usage.sawResult) return;
    try {
      await recordReportUsage(userId, 1, usage.totalTokens);
    } catch (e) {
      console.error("[knowledge-synthesis] failed to record usage:", e);
    }
  }, userId);
}
