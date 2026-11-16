import { Redis } from "@upstash/redis";

// How much each user has used the first Solution Wizard in the browser: the
// sessions they started, the messages they sent and when they last did either.
// The proxy counts a request the API accepted; /admin shows the counts. They
// live in Upstash Redis next to the rate limit and the trial allowance. Without
// Redis nothing is counted and /admin shows no numbers.

export type WizardUseKind = "session" | "message";

export interface WizardUse {
  sessions: number;
  messages: number;
  /** ISO time of the last counted request, or null when there is none. */
  lastAt: string | null;
}

/** The part of the Redis client this module uses, so a test can stand in for it. */
export interface WizardUseStore {
  hincrby(key: string, field: string, increment: number): Promise<unknown>;
  hset(key: string, fields: Record<string, string>): Promise<unknown>;
  hgetall(key: string): Promise<Record<string, unknown> | null>;
}

const PREFIX = "gaik-demo:wizard-use:";

let redis: Redis | null | undefined;
function getStore(): WizardUseStore | null {
  if (redis !== undefined) return redis;
  const url = process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.UPSTASH_REDIS_REST_TOKEN;
  redis = url && token ? new Redis({ url, token }) : null;
  return redis;
}

/** Which use a wizard API request is, or null for one that is not counted. */
export function wizardUseKind(
  method: string,
  pathname: string,
): WizardUseKind | null {
  if (method.toUpperCase() !== "POST") return null;
  if (pathname === "/api/wizard/start") return "session";
  if (pathname.startsWith("/api/wizard/message/")) return "message";
  return null;
}

/** Count one use for the user. Never throws: a count must not fail a request. */
export async function recordWizardUse(
  userId: string,
  kind: WizardUseKind,
  store: WizardUseStore | null = getStore(),
  now: Date = new Date(),
): Promise<void> {
  if (!store) return;
  const key = PREFIX + userId;
  try {
    await Promise.all([
      store.hincrby(key, kind === "session" ? "sessions" : "messages", 1),
      store.hset(key, { lastAt: now.toISOString() }),
    ]);
  } catch (error) {
    console.warn(
      "[wizard-usage] not counted:",
      error instanceof Error ? error.message : error,
    );
  }
}

function count(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
}

/**
 * The counts for these users, by user id. Null when nothing is counted (no
 * Redis, or it did not answer), so the page can say so instead of showing zeros.
 */
export async function readWizardUse(
  userIds: string[],
  store: WizardUseStore | null = getStore(),
): Promise<Record<string, WizardUse> | null> {
  if (!store) return null;
  try {
    const rows = await Promise.all(
      userIds.map((id) => store.hgetall(PREFIX + id)),
    );
    return Object.fromEntries(
      userIds.map((id, i) => [
        id,
        {
          sessions: count(rows[i]?.sessions),
          messages: count(rows[i]?.messages),
          lastAt:
            typeof rows[i]?.lastAt === "string"
              ? (rows[i]?.lastAt as string)
              : null,
        },
      ]),
    );
  } catch (error) {
    console.warn(
      "[wizard-usage] not read:",
      error instanceof Error ? error.message : error,
    );
    return null;
  }
}
