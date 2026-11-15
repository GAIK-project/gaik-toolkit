import { Ratelimit } from "@upstash/ratelimit";
import { Redis } from "@upstash/redis";

// Admin sign-in attempts: a few per client address per 15 minutes and a shared
// ceiling per hour for all addresses together, so the shared password can be
// tried only a few times, from one address or from many. The counts live in Upstash Redis,
// shared by every replica. Without Redis, or while it does not answer, each
// replica counts in its own memory, so the limit never switches off.

/** A positive integer from env, or the default. */
function countEnv(name: string, def: number): number {
  const raw = process.env[name];
  if (!raw) return def;
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) && n > 0 ? n : def;
}

export interface SignInLimits {
  /** Attempts one client address may make per 15 minutes. */
  perAddress: number;
  /** Attempts all addresses together may make per hour. */
  total: number;
}

/** Read at call time so `oc set env` changes apply without a rebuild. */
export function getSignInLimits(): SignInLimits {
  return {
    perAddress: countEnv("ADMIN_SIGN_IN_ATTEMPTS", 5),
    total: countEnv("ADMIN_SIGN_IN_ATTEMPTS_TOTAL", 30),
  };
}

const ADDRESS_WINDOW_MS = 15 * 60 * 1000;
const TOTAL_WINDOW_MS = 60 * 60 * 1000;

/** Fixed-window counters in this process's memory. */
export class MemoryWindows {
  private windows = new Map<string, { start: number; count: number }>();

  constructor(private now: () => number = Date.now) {}

  /** Count one attempt for `key`; false when the window already holds `limit`. */
  take(key: string, limit: number, windowMs: number): boolean {
    const now = this.now();
    const start = now - (now % windowMs);
    const current = this.windows.get(key);
    const entry =
      current && current.start === start ? current : { start, count: 0 };
    if (this.windows.size > 10_000) this.windows.clear();
    if (entry.count >= limit) {
      this.windows.set(key, entry);
      return false;
    }
    entry.count += 1;
    this.windows.set(key, entry);
    return true;
  }
}

const memory = new MemoryWindows();

let redis: Redis | null | undefined;
function getRedis(): Redis | null {
  if (redis !== undefined) return redis;
  const url = process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.UPSTASH_REDIS_REST_TOKEN;
  redis = url && token ? new Redis({ url, token }) : null;
  return redis;
}

function takeInMemory(address: string, limits: SignInLimits): boolean {
  return (
    memory.take(`address:${address}`, limits.perAddress, ADDRESS_WINDOW_MS) &&
    memory.take("total", limits.total, TOTAL_WINDOW_MS)
  );
}

/**
 * Count one admin sign-in attempt from `address`. False when the address or
 * all addresses together have used their attempts for the current window.
 */
export async function takeAdminSignInAttempt(
  address: string,
): Promise<boolean> {
  const limits = getSignInLimits();
  const client = getRedis();
  if (!client) return takeInMemory(address, limits);
  try {
    const perAddress = new Ratelimit({
      redis: client,
      limiter: Ratelimit.fixedWindow(limits.perAddress, "15 m"),
      prefix: "gaik-demo:admin-sign-in",
      analytics: false,
    });
    if (!(await perAddress.limit(address)).success) return false;
    const total = new Ratelimit({
      redis: client,
      limiter: Ratelimit.fixedWindow(limits.total, "1 h"),
      prefix: "gaik-demo:admin-sign-in-total",
      analytics: false,
    });
    return (await total.limit("all")).success;
  } catch (error) {
    console.warn(
      "[admin] Redis unavailable, sign-in attempts counted in memory:",
      error instanceof Error ? error.message : error,
    );
    return takeInMemory(address, limits);
  }
}
