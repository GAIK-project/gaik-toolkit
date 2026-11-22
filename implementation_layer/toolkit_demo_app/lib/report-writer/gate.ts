import { USER_HEADER } from "@/lib/api-access";
import { NextRequest, NextResponse } from "next/server";
import { createClient, createServiceClient } from "@/lib/supabase/server";
import { EMAIL_UNCONFIRMED, isEmailConfirmed } from "@/lib/api-access";
import { clientIp } from "@/lib/client-ip";
import { ADMIN_COOKIE_NAME, MODEL_TIER_HEADER, isModelStaff } from "@/lib/model-tier";
import { checkRateLimit, ratelimit } from "@/lib/rate-limit";
import {
  pickUsageFromEvents,
  type ReportUsageInfo,
} from "@/lib/report-writer/usage";
import { parseSSEEvents } from "@/lib/sse";
import { getTrialLimits, takeTrialRun, trialEnabled } from "@/lib/trial";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const BYPASS_AUTH = process.env.BYPASS_AUTH === "true";

export interface AccessRow {
  status: string;
  reports_count: number | null;
  report_limit_override: number | null;
}

export { clientIp };

/**
 * The 403 body for a user who is not approved or has used up their reports,
 * or null when the user may run. A per-user override wins over the default.
 * A pending user may write up to `trialReports` reports (0 turns that off).
 */
export function accessDenial(
  row: AccessRow | null,
  maxReports: number,
  trialReports = 0,
): Record<string, unknown> | null {
  const trial = row?.status === "pending" && trialReports > 0;
  if (!row || (row.status !== "approved" && !trial))
    return { error: "Your access is pending approval." };
  const used = row.reports_count ?? 0;
  const regularCap = row.report_limit_override ?? maxReports;
  const cap = trial ? Math.min(trialReports, regularCap) : regularCap;
  if (used >= cap)
    return trial
      ? {
          error: `You've used your ${cap === 1 ? "trial report" : `${cap} trial reports`}. Full access opens when your account is approved.`,
          used,
          limit: cap,
        }
      : {
          error: `You've used all ${cap} of your reports. Ask an admin to reset your counter.`,
          used,
          limit: cap,
        };
  return null;
}

/**
 * Auth + approval (or trial) + quota, then the per-IP burst limit (parity with the proxy;
 * these routes are not proxied). Returns the refusal response, or the user id
 * (null under BYPASS_AUTH) and whether the user may run the team-only models
 * (lib/model-tier.ts), read from the session like the proxy does.
 */
export async function gateReportWriter(
  request: NextRequest,
  maxReports: number,
): Promise<NextResponse | { userId: string | null; staff: boolean }> {
  if (BYPASS_AUTH)
    return {
      userId: null,
      // As in the proxy: without a session only the admin cookie counts.
      staff: isModelStaff(null, request.cookies.get(ADMIN_COOKIE_NAME)?.value),
    };

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
  const trialReports = trialEnabled() ? getTrialLimits().reports : 0;
  const denial = accessDenial(row as AccessRow | null, maxReports, trialReports);
  if (denial) return NextResponse.json(denial, { status: 403 });
  // The per-IP limit comes before the trial run, so a refused request spends
  // none. While the configured Redis does not answer, it refuses (503).
  const limited = await checkRateLimit(
    ratelimit,
    clientIp(request.headers),
    "Liian monta pyyntöä. Yritä hetken päästä uudelleen.",
    "[report-writer]",
  );
  if (limited) {
    return NextResponse.json(
      { error: limited.error },
      { status: limited.status, headers: limited.headers },
    );
  }

  // A pending user's stages also count against the daily trial allowance.
  if (row?.status === "pending") {
    if (!isEmailConfirmed(user))
      return NextResponse.json(
        { error: EMAIL_UNCONFIRMED.error },
        { status: EMAIL_UNCONFIRMED.status },
      );
    const trial = await takeTrialRun(user.id);
    if (!trial.ok)
      return NextResponse.json({ error: trial.error }, { status: trial.status });
  }

  const staff = isModelStaff(
    user.email?.toLowerCase() ?? null,
    request.cookies.get(ADMIN_COOKIE_NAME)?.value,
  );
  return { userId: user.id, staff };
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

/** Sent only by these route handlers; the generic proxy never forwards it. */
export const REPORT_RUN_HEADER = "x-gaik-report-run";

/**
 * The header that tells the backend this run passed the gate above. The API's
 * run routes refuse a run without it when REPORT_RUN_TOKEN is set on both
 * deployments (api/utils/report_runs.py).
 */
export function reportRunHeaders(): Record<string, string> {
  const token = process.env.REPORT_RUN_TOKEN;
  return token ? { [REPORT_RUN_HEADER]: token } : {};
}

/**
 * What a page shows for a backend refusal: the API's `detail` when it is a sentence,
 * as FastAPI sends it for a refused model or an invalid request; else the body as it
 * came. A `detail` that is not a string (a list of validation errors) stays raw.
 */
export function refusalMessage(body: string): string {
  try {
    const parsed: unknown = JSON.parse(body);
    if (parsed && typeof parsed === "object" && "detail" in parsed) {
      const { detail } = parsed as { detail: unknown };
      if (typeof detail === "string" && detail.trim()) return detail;
    }
  } catch {
    // Not JSON: show the body as it is.
  }
  return body || "Generation failed";
}

/**
 * POST the form to the backend and stream its SSE back. When the stream ends,
 * onEnd gets the folded result usage; if it throws, the client receives an
 * `error` event with its message instead of a silent miss. `staff` (from
 * gateReportWriter) tells the API the user may run the team-only models.
 */
export async function forwardReportRun(
  backendPath: string,
  body: FormData,
  staff: boolean,
  onEnd: (usage: ReportUsageInfo) => Promise<void>,
  userId: string | null = null,
): Promise<Response> {
  let backendRes: Response;
  try {
    backendRes = await fetch(`${BACKEND_URL}${backendPath}`, {
      method: "POST",
      // One headers object: the run token, the user (for the API's audit line,
      // api/utils/audit.py) and, for the team, the model tier.
      headers: {
        ...reportRunHeaders(),
        ...(userId ? { [USER_HEADER]: userId } : {}),
        ...(staff ? { [MODEL_TIER_HEADER]: "staff" } : {}),
      },
      body,
    });
  } catch (e) {
    // The reason names the backend's address; it goes to the log, not the page.
    const id = crypto.randomUUID().slice(0, 12);
    console.error(`[report-run] error id ${id}: backend request failed:`, e);
    return NextResponse.json(
      { error: `The demo API did not answer (error id ${id}). Try again in a moment.` },
      { status: 502 },
    );
  }

  if (!backendRes.ok || !backendRes.body) {
    // The pages show `error` as it is (in a toast or the run's error line).
    const text = await backendRes.text().catch(() => "");
    return NextResponse.json(
      { error: refusalMessage(text) },
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
