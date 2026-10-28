import { Ratelimit } from "@upstash/ratelimit";
import { Redis } from "@upstash/redis";
import { PENDING_DENIAL } from "@/lib/api-access";

// A signed-up user whose access request is still pending can try the demos at
// once instead of waiting for an admin, within a daily allowance per user. Sign-up
// is open, so a shared daily total also bounds what all pending accounts together
// can spend. The counts live in Upstash Redis; without it the trial is off and
// pending users wait for approval as before (fail closed).

/** A non-negative integer from env; 0 turns the limit's feature off. */
function countEnv(name: string, def: number): number {
  const raw = process.env[name];
  if (!raw) return def;
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) && n >= 0 ? n : def;
}

export interface TrialLimits {
  /** Runs (state-changing API requests) a pending user may make per day. */
  runsPerDay: number;
  /** Runs all pending users together may make per day. */
  runsPerDayTotal: number;
  /** Finished reports a pending user may write (Report Writer family). */
  reports: number;
}

/** Read at call time so `oc set env` changes apply without a rebuild. */
export function getTrialLimits(): TrialLimits {
  return {
    runsPerDay: countEnv("TRIAL_RUNS_PER_DAY", 30),
    runsPerDayTotal: countEnv("TRIAL_RUNS_PER_DAY_TOTAL", 300),
    reports: countEnv("TRIAL_REPORTS", 1),
  };
}

let redis: Redis | null | undefined;
function getRedis(): Redis | null {
  if (redis !== undefined) return redis;
  const url = process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.UPSTASH_REDIS_REST_TOKEN;
  redis = url && token ? new Redis({ url, token }) : null;
  return redis;
}

/** Whether pending users can run demos now. */
export function trialEnabled(): boolean {
  const limits = getTrialLimits();
  return limits.runsPerDay > 0 && limits.runsPerDayTotal > 0 && !!getRedis();
}

export type TrialResult =
  | { ok: true }
  | { ok: false; status: number; error: string };

/** Count one run against the pending user's daily allowance and the shared total. */
export async function takeTrialRun(userId: string): Promise<TrialResult> {
  const limits = getTrialLimits();
  const client = getRedis();
  if (!client || limits.runsPerDay === 0 || limits.runsPerDayTotal === 0)
    return { ok: false, ...PENDING_DENIAL };

  try {
    const perUser = new Ratelimit({
      redis: client,
      limiter: Ratelimit.fixedWindow(limits.runsPerDay, "1 d"),
      prefix: "gaik-demo:trial-user",
      analytics: false,
    });
    if (!(await perUser.limit(userId)).success)
      return {
        ok: false,
        status: 429,
        error: `You've used today's ${limits.runsPerDay} trial runs. Full access opens when your account is approved.`,
      };

    const total = new Ratelimit({
      redis: client,
      limiter: Ratelimit.fixedWindow(limits.runsPerDayTotal, "1 d"),
      prefix: "gaik-demo:trial-total",
      analytics: false,
    });
    if (!(await total.limit("all")).success)
      return {
        ok: false,
        status: 429,
        error:
          "Today's trial runs are used up. Full access opens when your account is approved.",
      };
  } catch (error) {
    console.warn(
      "[trial] Redis unavailable, trial runs off:",
      error instanceof Error ? error.message : error,
    );
    return { ok: false, ...PENDING_DENIAL };
  }
  return { ok: true };
}
