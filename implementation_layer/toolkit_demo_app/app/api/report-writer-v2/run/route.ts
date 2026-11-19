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
import { checkRunForm, type Stage } from "@/lib/report-writer/workspace";

/**
 * Report Writer v2 (CURACT) stage run. Every stage passes the same gate as the
 * legacy run; a report is counted when synthesize returns a result, and tokens
 * are recorded for every stage that reports them.
 */
export async function POST(request: NextRequest) {
  const limits = getReportWriterLimits();
  const bodyLimit = bodyLimitFor("/report-writer-v2/run");
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

  return forwardReportRun("/report-writer-v2/run", fwd, staff, async (usage) => {
    if (!userId || !usage.sawResult) return;
    const reports = stage === "synthesize" ? 1 : 0;
    if (!reports && !usage.totalTokens) return;
    try {
      await recordReportUsage(userId, reports, usage.totalTokens);
    } catch (e) {
      console.error("[report-writer-v2] failed to record usage:", e);
    }
  }, userId);
}
