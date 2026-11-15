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

/**
 * Fixed-window counters in this process's memory, for at most `maxKeys` keys.
 * When the map is full, windows that have ended are dropped; if it is still
 * full, a new key is refused. A window still running is never dropped, so no
 * count, the shared ceiling's included, starts over early.
 */
export class MemoryWindows {
  private windows = new Map<
    string,
    { start: number; end: number; count: number }
  >();

  constructor(
    private now: () => number = Date.now,
    private maxKeys = 10_000,
  ) {}

  /** Count one attempt for `key`; false when the window already holds `limit`. */
  take(key: string, limit: number, windowMs: number): boolean {
    const now = this.now();
    const start = now - (now % windowMs);
    let entry = this.windows.get(key);
    if (!entry || entry.start !== start) {
      if (!entry && this.windows.size >= this.maxKeys) {
        for (const [k, e] of this.windows)
          if (e.end <= now) this.windows.delete(k);
        if (this.windows.size >= this.maxKeys) return false;
      }
      entry = { start, end: start + windowMs, count: 0 };
      this.windows.set(key, entry);
    }
    if (entry.count >= limit) return false;
    entry.count += 1;
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

function takeInMemory(
  address: string,
  limits: SignInLimits,
  windows: MemoryWindows,
): boolean {
  return (
    windows.take(`address:${address}`, limits.perAddress, ADDRESS_WINDOW_MS) &&
    windows.take("total", limits.total, TOTAL_WINDOW_MS)
  );
}

/** One shared counter: a Redis rate limit, or a stand-in in the tests. */
export type SharedLimit = (
  prefix: string,
  limit: number,
  window: "15 m" | "1 h",
  key: string,
) => Promise<{ success: boolean; reason?: string }>;

function redisLimit(client: Redis): SharedLimit {
  return (prefix, limit, window, key) =>
    new Ratelimit({
      redis: client,
      limiter: Ratelimit.fixedWindow(limit, window),
      prefix,
      analytics: false,
    }).limit(key);
}

/**
 * Count one attempt from `address` in `shared` counters, or in `windows` when
 * there are none or they do not answer. Upstash's rate limit lets a request
 * through after its own timeout instead of failing (`reason: "timeout"`), so a
 * timed-out answer is counted in memory too.
 */
export async function takeAttempt(
  shared: SharedLimit | null,
  address: string,
  limits: SignInLimits,
  windows: MemoryWindows = memory,
): Promise<boolean> {
  if (!shared) return takeInMemory(address, limits, windows);
  try {
    const byAddress = await shared(
      "gaik-demo:admin-sign-in",
      limits.perAddress,
      "15 m",
      address,
    );
    if (byAddress.reason === "timeout")
      return takeInMemory(address, limits, windows);
    if (!byAddress.success) return false;
    const all = await shared(
      "gaik-demo:admin-sign-in-total",
      limits.total,
      "1 h",
      "all",
    );
    if (all.reason === "timeout") return takeInMemory(address, limits, windows);
    return all.success;
  } catch (error) {
    console.warn(
      "[admin] Redis unavailable, sign-in attempts counted in memory:",
      error instanceof Error ? error.message : error,
    );
    return takeInMemory(address, limits, windows);
  }
}

/**
 * Count one admin sign-in attempt from `address`. False when the address or
 * all addresses together have used their attempts for the current window.
 */
export async function takeAdminSignInAttempt(
  address: string,
): Promise<boolean> {
  const client = getRedis();
  return takeAttempt(
    client ? redisLimit(client) : null,
    address,
    getSignInLimits(),
  );
}
