// Bounds repeated dev sign-in attempts (app/login/actions.ts, devSignIn).
//
// A dev-auth instance is reachable from the internet and checks passwords
// itself, so without a bound anyone can try passwords as fast as the server
// answers. Failed attempts are counted per account and per client address;
// after `maxFailures` failures within `windowMs`, that account or address is
// refused for `lockoutMs`, with the same generic message as a wrong password.
//
// In-memory on purpose: the web app runs as one replica
// (deploy/openshift/deployment-web.yaml). The counts are lost on a restart
// and are not shared between processes; more than one replica would need a
// shared store (Redis, Postgres) instead.

export type ThrottleConfig = {
  maxFailures: number;
  windowMs: number;
  lockoutMs: number;
};

export const DEFAULT_THROTTLE: ThrottleConfig = {
  maxFailures: 5,
  windowMs: 10 * 60 * 1000,
  lockoutMs: 10 * 60 * 1000,
};

function positiveInt(raw: string | undefined, fallback: number): number {
  const value = Number(raw?.trim());
  return Number.isInteger(value) && value > 0 ? value : fallback;
}

/**
 * WIZARD_DEV_LOGIN_MAX_FAILURES (default 5), WIZARD_DEV_LOGIN_WINDOW_S
 * (default 600) and WIZARD_DEV_LOGIN_LOCKOUT_S (default 600). A value that is
 * not a positive integer falls back to the default rather than switching the
 * bound off.
 */
export function throttleConfig(env: NodeJS.ProcessEnv = process.env): ThrottleConfig {
  return {
    maxFailures: positiveInt(env.WIZARD_DEV_LOGIN_MAX_FAILURES, DEFAULT_THROTTLE.maxFailures),
    windowMs: positiveInt(env.WIZARD_DEV_LOGIN_WINDOW_S, DEFAULT_THROTTLE.windowMs / 1000) * 1000,
    lockoutMs:
      positiveInt(env.WIZARD_DEV_LOGIN_LOCKOUT_S, DEFAULT_THROTTLE.lockoutMs / 1000) * 1000,
  };
}

type Entry = { failures: number[]; blockedUntil: number };

/**
 * Keys kept at most, so memory stays bounded. The oldest key that is not
 * refused right now makes room; a refused key is never dropped, or enough
 * failures on made-up accounts would end a lockout early.
 */
const MAX_KEYS = 10_000;

export class FailureCounter {
  private readonly entries = new Map<string, Entry>();

  constructor(private readonly config: ThrottleConfig = DEFAULT_THROTTLE) {}

  private live(key: string, now: number): Entry | undefined {
    const entry = this.entries.get(key);
    if (!entry) return undefined;
    entry.failures = entry.failures.filter((t) => now - t < this.config.windowMs);
    if (entry.blockedUntil <= now && entry.failures.length === 0) {
      this.entries.delete(key);
      return undefined;
    }
    return entry;
  }

  /** Whether `key` is refused right now. */
  isBlocked(key: string, now: number = Date.now()): boolean {
    const entry = this.live(key, now);
    return !!entry && entry.blockedUntil > now;
  }

  /** Count one failed attempt; blocks the key once it reaches the limit. */
  recordFailure(key: string, now: number = Date.now()): void {
    let entry = this.live(key, now);
    if (!entry) {
      if (this.entries.size >= MAX_KEYS && !this.makeRoom(now)) return;
      entry = { failures: [], blockedUntil: 0 };
      this.entries.set(key, entry);
    }
    entry.failures.push(now);
    if (entry.failures.length >= this.config.maxFailures) {
      entry.blockedUntil = now + this.config.lockoutMs;
      entry.failures = [];
    }
  }

  /** Drop the oldest key not refused at `now`; false when every key is refused. */
  private makeRoom(now: number): boolean {
    for (const [key, entry] of this.entries) {
      if (entry.blockedUntil <= now) {
        this.entries.delete(key);
        return true;
      }
    }
    return false;
  }

  /** Forget the failures of `key` (an account that just signed in). */
  reset(key: string): void {
    this.entries.delete(key);
  }

  get size(): number {
    return this.entries.size;
  }
}

/**
 * The client address from X-Forwarded-For, or null. The header is set by
 * whoever sends the request, so it is read only when the deployment says how
 * many proxies in front of the app append to it (WIZARD_TRUSTED_PROXY_HOPS;
 * 1 for the Rahti router). The client is then the entry that many places
 * from the right: entries further left were written by the client itself.
 * Without the setting the header is ignored and only the per-account bound
 * applies.
 */
export function clientAddress(
  forwardedFor: string | null | undefined,
  env: NodeJS.ProcessEnv = process.env,
): string | null {
  const hops = Number(env.WIZARD_TRUSTED_PROXY_HOPS?.trim() ?? "");
  if (!Number.isInteger(hops) || hops <= 0 || !forwardedFor) return null;
  const entries = forwardedFor
    .split(",")
    .map((e) => e.trim())
    .filter(Boolean);
  if (entries.length < hops) return null;
  return entries[entries.length - hops] || null;
}

export function accountKey(email: string): string {
  return `account:${email.trim().toLowerCase()}`;
}

export function addressKey(address: string): string {
  return `address:${address}`;
}

let counter: FailureCounter | null = null;

/** The process-wide counter for dev sign-in, built from the env on first use. */
export function devLoginCounter(): FailureCounter {
  counter ??= new FailureCounter(throttleConfig());
  return counter;
}

/** Tests only: start from an empty counter (with the env as it is now). */
export function resetDevLoginCounter(): void {
  counter = null;
}
