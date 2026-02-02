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
    // 100 req/min allows ~5 req/min per user with 20 users behind same IP (NAT)
    limiter: Ratelimit.slidingWindow(100, "1 m"),
    analytics: true,
    prefix: "gaik-demo",
  });
}

export const ratelimit = createRateLimiter();
