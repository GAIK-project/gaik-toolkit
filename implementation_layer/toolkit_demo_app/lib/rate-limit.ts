import { Ratelimit } from "@upstash/ratelimit";
import { Redis } from "@upstash/redis";

/**
 * Rate limiter using Upstash Redis
 * Sliding window: 10 requests per minute per IP
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
    // 10 req/min per IP
    limiter: Ratelimit.slidingWindow(10, "1 m"),
    analytics: true,
    prefix: "gaik-demo",
  });
}

export const ratelimit = createRateLimiter();
