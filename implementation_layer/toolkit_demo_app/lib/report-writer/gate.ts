import { NextRequest, NextResponse } from "next/server";
import { createClient, createServiceClient } from "@/lib/supabase/server";
import { ratelimit } from "@/lib/rate-limit";
import {
  pickUsageFromEvents,
  type ReportUsageInfo,
} from "@/lib/report-writer/usage";
import { parseSSEEvents } from "@/lib/sse";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const BYPASS_AUTH = process.env.BYPASS_AUTH === "true";

export interface AccessRow {
  status: string;
  reports_count: number | null;
  report_limit_override: number | null;
}

/** First hop of x-forwarded-for, then x-real-ip, else "anonymous". */
export function clientIp(headers: Headers): string {
  return (
    headers.get("x-forwarded-for")?.split(",")[0]?.trim() ??
    headers.get("x-real-ip") ??
    "anonymous"
  );
}

/**
 * The 403 body for a user who is not approved or has used up their reports,
 * or null when the user may run. A per-user override wins over the default.
 */
export function accessDenial(
  row: AccessRow | null,
  maxReports: number,
): Record<string, unknown> | null {
  if (!row || row.status !== "approved")
    return { error: "Your access is pending approval." };
  const used = row.reports_count ?? 0;
  const cap = row.report_limit_override ?? maxReports;
  if (used >= cap)
    return {
      error: `You've used all ${cap} of your reports. Ask an admin to reset your counter.`,
      used,
      limit: cap,
    };
  return null;
}

/**
 * Auth + approval + quota, then the per-IP burst limit (parity with the proxy;
 * these routes are not proxied). Returns the refusal response, or the user id
 * (null under BYPASS_AUTH).
 */
export async function gateReportWriter(
  request: NextRequest,
  maxReports: number,
): Promise<NextResponse | { userId: string | null }> {
  if (BYPASS_AUTH) return { userId: null };

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

  const { data: row } = await supabase
    .from("access_requests")
    .select("status, reports_count, report_limit_override")
    .eq("user_id", user.id)
    .single();
  const denial = accessDenial(row as AccessRow | null, maxReports);
  if (denial) return NextResponse.json(denial, { status: 403 });

  if (ratelimit) {
    try {
      const { success, limit, remaining, reset } = await ratelimit.limit(
        clientIp(request.headers),
      );
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

  return { userId: user.id };
}

/** Add a run's report count and tokens to the user's access_requests row. */
export async function recordReportUsage(
  userId: string,
  reports: number,
  tokens: number,
): Promise<void> {
  const svc = createServiceClient();
  const { data: cur, error: readError } = await svc
    .from("access_requests")
    .select("reports_count, report_tokens_used")
    .eq("user_id", userId)
    .single();
  if (readError) throw new Error(`Reading usage failed: ${readError.message}`);
  const { error } = await svc
    .from("access_requests")
    .update({
      reports_count: ((cur?.reports_count as number) ?? 0) + reports,
      report_tokens_used:
        ((cur?.report_tokens_used as number) ?? 0) + tokens,
      last_report_at: new Date().toISOString(),
    })
    .eq("user_id", userId);
  if (error) throw new Error(`Recording usage failed: ${error.message}`);
}

/**
 * POST the form to the backend and stream its SSE back. When the stream ends,
 * onEnd gets the folded result usage; if it throws, the client receives an
 * `error` event with its message instead of a silent miss.
 */
export async function forwardReportRun(
  backendPath: string,
  body: FormData,
  onEnd: (usage: ReportUsageInfo) => Promise<void>,
): Promise<Response> {
  let backendRes: Response;
  try {
    backendRes = await fetch(`${BACKEND_URL}${backendPath}`, {
      method: "POST",
      body,
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

  // Tee the SSE stream: pass through to the client AND fold result usage so
  // onEnd can record the run. Failed runs aren't charged.
  const decoder = new TextDecoder();
  let buf = "";
  let usage: ReportUsageInfo = { sawResult: false, totalTokens: 0 };

  const tee = new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      controller.enqueue(chunk);
      buf += decoder.decode(chunk, { stream: true });
      const { events, remaining } = parseSSEEvents(buf);
      buf = remaining;
      usage = pickUsageFromEvents(events, usage);
    },
    async flush(controller) {
      if (buf.trim()) {
        const { events } = parseSSEEvents(`${buf}\n\n`);
        usage = pickUsageFromEvents(events, usage);
      }
      try {
        await onEnd(usage);
      } catch (e) {
        const message = e instanceof Error ? e.message : String(e);
        controller.enqueue(
          new TextEncoder().encode(
            `event: error\ndata: ${JSON.stringify({ message })}\n\n`,
          ),
        );
      }
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
