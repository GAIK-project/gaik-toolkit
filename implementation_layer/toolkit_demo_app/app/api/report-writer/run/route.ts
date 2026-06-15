import { NextRequest, NextResponse } from "next/server";
import { createClient, createServiceClient } from "@/lib/supabase/server";
import { ratelimit } from "@/lib/rate-limit";
import { getReportWriterLimits } from "@/lib/report-writer/limits";
import {
  pickUsageFromEvents,
  type ReportUsageInfo,
} from "@/lib/report-writer/usage";
import { parseSSEEvents } from "@/lib/sse";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const BYPASS_AUTH = process.env.BYPASS_AUTH === "true";

/**
 * Report Writer run endpoint. Carved out of the generic proxy so it can enforce
 * a per-user quota, bound the run size, stream the backend SSE through, and
 * record actual token usage on success.
 */
export async function POST(request: NextRequest) {
  const limits = getReportWriterLimits();
  let userId: string | null = null;

  // 1) Auth + approval + quota
  if (!BYPASS_AUTH) {
    const supabase = await createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (!user) {
      return NextResponse.json(
        { error: "Sign in to use the Report Writer." },
        { status: 401 },
      );
    }
    userId = user.id;

    const { data: row } = await supabase
      .from("access_requests")
      .select("status, reports_count, report_limit_override")
      .eq("user_id", user.id)
      .single();

    if (!row || row.status !== "approved") {
      return NextResponse.json(
        { error: "Your access is pending approval." },
        { status: 403 },
      );
    }

    const used = (row.reports_count as number) ?? 0;
    // Per-user override wins over the global default (e.g. demo/team accounts).
    const cap =
      (row.report_limit_override as number | null) ?? limits.maxReports;
    if (used >= cap) {
      return NextResponse.json(
        {
          error: `You've used all ${cap} of your reports. Ask an admin to reset your counter.`,
          used,
          limit: cap,
        },
        { status: 403 },
      );
    }
  }

  // 2) Per-IP burst limit (parity with the proxy; this route is not proxied)
  if (ratelimit && !BYPASS_AUTH) {
    try {
      const ip =
        request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ??
        request.headers.get("x-real-ip") ??
        "anonymous";
      const { success, limit, remaining, reset } = await ratelimit.limit(ip);
      if (!success) {
        return NextResponse.json(
          { error: "Liian monta pyyntöä. Yritä hetken päästä uudelleen." },
          {
            status: 429,
            headers: {
              "X-RateLimit-Limit": limit.toString(),
              "X-RateLimit-Remaining": remaining.toString(),
              "X-RateLimit-Reset": reset.toString(),
            },
          },
        );
      }
    } catch (e) {
      console.warn(
        "[report-writer] rate limit skipped:",
        e instanceof Error ? e.message : e,
      );
    }
  }

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

  // Clamp the evidence ceiling so a single run stays bounded.
  const existingEvidence =
    typeof config.max_evidence_chars === "number"
      ? config.max_evidence_chars
      : null;
  config.max_evidence_chars =
    existingEvidence == null
      ? limits.maxEvidenceChars
      : Math.min(existingEvidence, limits.maxEvidenceChars);

  // 4) Rebuild FormData (buffered Files) for forwarding — avoids the standalone
  //    request-stream truncation the proxy works around.
  const fwd = new FormData();
  for (const f of files) fwd.append("files", f, f.name);
  if (sample instanceof File) fwd.append("sample_report", sample, sample.name);
  fwd.append("config", JSON.stringify(config));

  // 5) Forward to the backend
  let backendRes: Response;
  try {
    backendRes = await fetch(`${BACKEND_URL}/report-writer/run`, {
      method: "POST",
      body: fwd,
    });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Backend error" },
      { status: 502 },
    );
  }

  if (!backendRes.ok || !backendRes.body) {
    const text = await backendRes.text().catch(() => "");
    return NextResponse.json(
      { error: text || "Generation failed" },
      { status: backendRes.status || 502 },
    );
  }

  // 6) Tee the SSE stream: pass through to the client AND, on a successful
  //    result event, record the run (count + tokens). Failed runs aren't charged.
  const decoder = new TextDecoder();
  let buf = "";
  let usage: ReportUsageInfo = { sawResult: false, totalTokens: 0 };

  const recordUsage = async () => {
    if (BYPASS_AUTH || !userId || !usage.sawResult) return;
    try {
      const svc = createServiceClient();
      const { data: cur } = await svc
        .from("access_requests")
        .select("reports_count, report_tokens_used")
        .eq("user_id", userId)
        .single();
      await svc
        .from("access_requests")
        .update({
          reports_count: ((cur?.reports_count as number) ?? 0) + 1,
          report_tokens_used:
            ((cur?.report_tokens_used as number) ?? 0) + usage.totalTokens,
          last_report_at: new Date().toISOString(),
        })
        .eq("user_id", userId);
    } catch (e) {
      console.error("[report-writer] failed to record usage:", e);
    }
  };

  const tee = new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      controller.enqueue(chunk);
      buf += decoder.decode(chunk, { stream: true });
      const { events, remaining } = parseSSEEvents(buf);
      buf = remaining;
      usage = pickUsageFromEvents(events, usage);
    },
    async flush() {
      if (buf.trim()) {
        const { events } = parseSSEEvents(`${buf}\n\n`);
        usage = pickUsageFromEvents(events, usage);
      }
      await recordUsage();
    },
  });

  return new Response(backendRes.body.pipeThrough(tee), {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      "X-Accel-Buffering": "no",
    },
  });
}
