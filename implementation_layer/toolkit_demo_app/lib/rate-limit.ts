import { Ratelimit } from "@upstash/ratelimit";
import { Redis } from "@upstash/redis";

/**
 * Rate limiter using Upstash Redis
 * Fixed window: 30 requests per minute per IP (POST only, see proxy.ts)
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
    redis: new Redis({ url, token }),
    // 30 req/min per IP (POST only — see proxy.ts)
    limiter: Ratelimit.fixedWindow(30, "1 m"),
    analytics: false,
    prefix: "gaik-demo",
  });
}

export const ratelimit = createRateLimiter();
