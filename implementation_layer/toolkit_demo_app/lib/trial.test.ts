import { afterEach, expect, test } from "bun:test";
import { Redis } from "@upstash/redis";
import {
  TRIAL_COUNTER_UNAVAILABLE,
  getTrialLimits,
  takeTrialRun,
} from "./trial";

const KEYS = [
  "TRIAL_RUNS_PER_DAY",
  "TRIAL_RUNS_PER_DAY_TOTAL",
  "TRIAL_REPORTS",
];
const saved = Object.fromEntries(KEYS.map((k) => [k, process.env[k]]));

afterEach(() => {
  for (const k of KEYS) {
    if (saved[k] === undefined) delete process.env[k];
    else process.env[k] = saved[k];
  }
});

test("limits default, read env, accept 0 and ignore junk", () => {
  for (const k of KEYS) delete process.env[k];
  expect(getTrialLimits()).toEqual({
    runsPerDay: 30,
    runsPerDayTotal: 300,
    reports: 1,
  });
  process.env.TRIAL_RUNS_PER_DAY = "0";
  process.env.TRIAL_RUNS_PER_DAY_TOTAL = "50";
  process.env.TRIAL_REPORTS = "-2";
  expect(getTrialLimits()).toEqual({
    runsPerDay: 0,
    runsPerDayTotal: 50,
    reports: 1,
  });
});

test("without Redis the trial is off and a pending user waits", async () => {
  if (process.env.UPSTASH_REDIS_REST_URL) return;
  expect(await takeTrialRun("user-1")).toEqual({
    ok: false,
    status: 403,
    error: "Your access is pending approval.",
  });
});

test("while the configured Redis does not answer, a trial run is refused", async () => {
  for (const k of KEYS) delete process.env[k];
  // Nothing listens on port 9; the request fails at once.
  const silent = new Redis({
    url: "http://127.0.0.1:9",
    token: "test",
    retry: false,
  });
  expect(await takeTrialRun("user-1", silent)).toEqual({
    ok: false,
    ...TRIAL_COUNTER_UNAVAILABLE,
  });
  expect(TRIAL_COUNTER_UNAVAILABLE.status).toBe(503);
});
