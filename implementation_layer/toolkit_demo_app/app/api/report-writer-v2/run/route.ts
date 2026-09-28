import { NextRequest, NextResponse } from "next/server";
import {
  forwardReportRun,
  gateReportWriter,
  recordReportUsage,
} from "@/lib/report-writer/gate";
import { getReportWriterLimits } from "@/lib/report-writer/limits";
import { checkRunForm, type Stage } from "@/lib/report-writer/workspace";

/**
 * Report Writer v2 (CURACT) stage run. Every stage passes the same gate as the
 * legacy run; a report is counted when synthesize returns a result, and tokens
 * are recorded for every stage that reports them.
 */
export async function POST(request: NextRequest) {
  const limits = getReportWriterLimits();
  const gate = await gateReportWriter(request, limits.maxReports);
  if (gate instanceof Response) return gate;
  const { userId } = gate;

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return NextResponse.json({ error: "Invalid form data." }, { status: 400 });
  }
  const invalid = checkRunForm(form, limits);
  if (invalid) {
    return NextResponse.json({ error: invalid.error }, { status: invalid.status });
  }
  const stage = form.get("stage") as Stage;

  // Rebuild FormData (buffered Files) for forwarding, like the legacy route.
  const fwd = new FormData();
  for (const key of ["stage", "spec"]) fwd.append(key, form.get(key) as string);
  // A file part: the backend caps plain form fields at 1 MB, and the workspace grows.
  fwd.append(
    "artifacts",
    new Blob([form.get("artifacts") as string], { type: "application/json" }),
    "artifacts.json",
  );
  for (const key of ["files", "sample_report"])
    for (const f of form.getAll(key) as File[]) fwd.append(key, f, f.name);

  return forwardReportRun("/report-writer-v2/run", fwd, async (usage) => {
    if (!userId || !usage.sawResult) return;
    const reports = stage === "synthesize" ? 1 : 0;
    if (!reports && !usage.totalTokens) return;
    try {
      await recordReportUsage(userId, reports, usage.totalTokens);
    } catch (e) {
      console.error("[report-writer-v2] failed to record usage:", e);
    }
  });
}
