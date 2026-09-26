import { NextRequest, NextResponse } from "next/server";
import {
  forwardReportRun,
  gateReportWriter,
  recordReportUsage,
} from "@/lib/report-writer/gate";
import { getReportWriterLimits } from "@/lib/report-writer/limits";

/**
 * Report Writer run endpoint. Carved out of the generic proxy so it can enforce
 * a per-user quota, bound the run size, stream the backend SSE through, and
 * record actual token usage on success.
 */
export async function POST(request: NextRequest) {
  const limits = getReportWriterLimits();

  // 1) Auth + approval + quota, 2) per-IP burst limit
  const gate = await gateReportWriter(request, limits.maxReports);
  if (gate instanceof Response) return gate;
  const { userId } = gate;

  // 3) Parse + validate the multipart body
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return NextResponse.json({ error: "Invalid form data." }, { status: 400 });
  }

  const files = form.getAll("files").filter((f): f is File => f instanceof File);
  const sample = form.get("sample_report");
  const configRaw = form.get("config");

  if (files.length === 0) {
    return NextResponse.json(
      { error: "No input files provided." },
      { status: 400 },
    );
  }

  let totalBytes = files.reduce((n, f) => n + f.size, 0);
  if (sample instanceof File) totalBytes += sample.size;
  if (totalBytes > limits.maxUploadMb * 1024 * 1024) {
    return NextResponse.json(
      { error: `Uploads exceed the ${limits.maxUploadMb} MB limit.` },
      { status: 413 },
    );
  }

  if (typeof configRaw !== "string") {
    return NextResponse.json({ error: "Missing config." }, { status: 400 });
  }
  let config: Record<string, unknown>;
  try {
    config = JSON.parse(configRaw);
  } catch {
    return NextResponse.json({ error: "Invalid config JSON." }, { status: 400 });
  }

  const sections = Array.isArray(config.sections) ? config.sections : [];
  if (sections.length > limits.maxSections) {
    return NextResponse.json(
      { error: `Too many sections (max ${limits.maxSections}).` },
      { status: 400 },
    );
  }

  // Clamp the evidence ceiling so a single run stays bounded. A requested value
  // is capped at the limit; an unset value defaults to it.
  config.max_evidence_chars =
    typeof config.max_evidence_chars === "number"
      ? Math.min(config.max_evidence_chars, limits.maxEvidenceChars)
      : limits.maxEvidenceChars;

  // 4) Rebuild FormData (buffered Files) for forwarding — avoids the standalone
  //    request-stream truncation the proxy works around.
  const fwd = new FormData();
  for (const f of files) fwd.append("files", f, f.name);
  if (sample instanceof File) fwd.append("sample_report", sample, sample.name);
  fwd.append("config", JSON.stringify(config));

  // 5) Forward to the backend, 6) record the run (count + tokens) when a result
  //    event arrived. Failed runs aren't charged.
  return forwardReportRun("/report-writer/run", fwd, async (usage) => {
    if (!userId || !usage.sawResult) return;
    try {
      await recordReportUsage(userId, 1, usage.totalTokens);
    } catch (e) {
      console.error("[report-writer] failed to record usage:", e);
    }
  });
}
