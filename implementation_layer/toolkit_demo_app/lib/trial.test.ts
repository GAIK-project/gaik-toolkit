import { afterEach, expect, test } from "bun:test";
import { Redis } from "@upstash/redis";
import {
  TRIAL_COUNTER_UNAVAILABLE,
  getTrialLimits,
  takeTrialRun,
  withinTrialWindow,
} from "./trial";

const KEYS = [
  "TRIAL_RUNS_PER_DAY",
  "TRIAL_RUNS_PER_DAY_TOTAL",
  "TRIAL_REPORTS",
  "TRIAL_HOURS",
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
    hours: 72,
  });
  process.env.TRIAL_RUNS_PER_DAY = "0";
  process.env.TRIAL_RUNS_PER_DAY_TOTAL = "50";
  process.env.TRIAL_REPORTS = "-2";
  expect(getTrialLimits()).toEqual({
    runsPerDay: 0,
    runsPerDayTotal: 50,
    reports: 1,
    hours: 72,
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

test("the trial lasts TRIAL_HOURS after sign-up, 72 by default", () => {
  delete process.env.TRIAL_HOURS;
  const now = Date.parse("2026-11-30T12:00:00Z");
  // Signed up on Friday evening, reviewed on Monday morning: still on trial.
  expect(withinTrialWindow("2026-11-27T19:00:00Z", now)).toBe(true);
  expect(withinTrialWindow("2026-11-27T11:59:00Z", now)).toBe(false);
  process.env.TRIAL_HOURS = "48";
  expect(withinTrialWindow("2026-11-27T19:00:00Z", now)).toBe(false);
});

test("TRIAL_HOURS=0 keeps the trial until approval; an unknown sign-up time ends it", () => {
  process.env.TRIAL_HOURS = "0";
  expect(withinTrialWindow("2020-01-01T00:00:00Z")).toBe(true);
  delete process.env.TRIAL_HOURS;
  expect(withinTrialWindow(undefined)).toBe(false);
  expect(withinTrialWindow("not a date")).toBe(false);
});
