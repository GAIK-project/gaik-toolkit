import { Ratelimit } from "@upstash/ratelimit";
import { Redis } from "@upstash/redis";

/**
 * One quick retry: the default (five retries, about 4 s of backoff) outlasts
 * Ratelimit's 5 s timeout, which then lets the request through uncounted.
 */
export const LIMITER_RETRY = { retries: 1, backoff: () => 100 };

/**
 * Rate limiter using Upstash Redis
 * Fixed window: 15 POST requests per minute per IP (see proxy.ts)
 * Falls back to no rate limiting if Redis is not configured (dev environment)
 */
function createRateLimiter(): Ratelimit | null {
  const url = process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.UPSTASH_REDIS_REST_TOKEN;

  if (!url || !token) {
    console.warn(
      "[rate-limit] UPSTASH_REDIS_REST_URL or UPSTASH_REDIS_REST_TOKEN not set. Rate limiting disabled.",
    );
    return null;
  }

  return new Ratelimit({
    redis: new Redis({ url, token, retry: LIMITER_RETRY }),
    // 15 POST req/min per IP (see proxy.ts)
    limiter: Ratelimit.fixedWindow(15, "1 m"),
    analytics: false,
    prefix: "gaik-demo",
  });
}

export const ratelimit = createRateLimiter();

export interface LimitRefusal {
  status: number;
  error: string;
  headers?: Record<string, string>;
}

/** The refusal while Redis is configured but does not answer. */
export const LIMITER_UNAVAILABLE: LimitRefusal = {
  status: 503,
  error:
    "The request limit cannot be checked right now. Try again in a few minutes.",
};

/**
 * Count one request for `key`. Null when it may run: within the limit, or no
 * limiter is configured (local dev). A request over the limit gets a 429, and
 * one that arrives while the configured Redis does not answer gets a 503: the
 * limiter refuses rather than letting requests through uncounted.
 */
export async function checkRateLimit(
  limiter: Pick<Ratelimit, "limit"> | null,
  key: string,
  tooMany: string,
  logTag: string,
): Promise<LimitRefusal | null> {
  if (!limiter) return null;
  try {
    const { success, limit, remaining, reset, reason } =
      await limiter.limit(key);
    // On its timeout Ratelimit answers success with reason "timeout": the
    // request was not counted, so it is refused like an error.
    if (reason === "timeout") throw new Error("Redis did not answer in time");
    if (success) return null;
    return {
      status: 429,
      error: tooMany,
      headers: {
        "X-RateLimit-Limit": limit.toString(),
        "X-RateLimit-Remaining": remaining.toString(),
        "X-RateLimit-Reset": reset.toString(),
      },
    };
  } catch (error) {
    console.warn(
      `${logTag} Redis does not answer, request refused:`,
      error instanceof Error ? error.message : error,
    );
    return LIMITER_UNAVAILABLE;
  }
}
