import { expect, test } from "bun:test";
import { LIMITER_UNAVAILABLE, checkRateLimit } from "./rate-limit";

const result = (success: boolean) => ({
  success,
  limit: 15,
  remaining: success ? 14 : 0,
  reset: 1_700_000_000_000,
  pending: Promise.resolve(),
});

test("without a configured limiter every request runs", async () => {
  expect(await checkRateLimit(null, "1.2.3.4", "Too many", "[t]")).toBeNull();
});

test("a request within the limit runs", async () => {
  const limiter = { limit: async () => result(true) };
  expect(
    await checkRateLimit(limiter, "1.2.3.4", "Too many", "[t]"),
  ).toBeNull();
});

test("a request over the limit gets a 429 with the limit headers", async () => {
  const limiter = { limit: async () => result(false) };
  expect(await checkRateLimit(limiter, "1.2.3.4", "Too many", "[t]")).toEqual({
    status: 429,
    error: "Too many",
    headers: {
      "X-RateLimit-Limit": "15",
      "X-RateLimit-Remaining": "0",
      "X-RateLimit-Reset": "1700000000000",
    },
  });
});

test("while the configured Redis does not answer, the request is refused", async () => {
  const limiter = {
    limit: async (): Promise<ReturnType<typeof result>> => {
      throw new Error("fetch failed");
    },
  };
  const refusal = await checkRateLimit(limiter, "1.2.3.4", "Too many", "[t]");
  expect(refusal).toEqual(LIMITER_UNAVAILABLE);
  expect(refusal?.status).toBe(503);
});

test("a limiter answer that timed out is refused, not let through", async () => {
  const limiter = {
    limit: async () => ({ ...result(true), reason: "timeout" as const }),
  };
  expect(await checkRateLimit(limiter, "1.2.3.4", "Too many", "[t]")).toEqual(
    LIMITER_UNAVAILABLE,
  );
});
