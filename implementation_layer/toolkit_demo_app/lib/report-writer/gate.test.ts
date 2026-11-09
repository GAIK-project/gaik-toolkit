import { expect, test } from "bun:test";
import { accessDenial, clientIp } from "./gate";

const row = (over: object = {}) => ({
  status: "approved",
  reports_count: 0,
  report_limit_override: null,
  ...over,
});

test("the report gate keys on the router-added address", () => {
  expect(clientIp(new Headers({ "x-forwarded-for": "1.2.3.4, 203.0.113.7" }))).toBe("203.0.113.7");
});

test("a missing or unapproved row is pending approval", () => {
  const pending = { error: "Your access is pending approval." };
  expect(accessDenial(null, 5)).toEqual(pending);
  expect(accessDenial(row({ status: "pending" }), 5)).toEqual(pending);
});

test("a pending user may write the trial reports, within the regular cap", () => {
  const trialRow = row({ status: "pending" });
  expect(accessDenial(trialRow, 5, 1)).toBeNull();
  expect(accessDenial(row({ status: "pending", reports_count: 1 }), 5, 1)).toEqual({
    error: "You've used your trial report. Full access opens when your account is approved.",
    used: 1,
    limit: 1,
  });
  expect(accessDenial(row({ status: "pending", reports_count: 2 }), 5, 3)).toBeNull();
  expect(accessDenial(row({ status: "pending", report_limit_override: 0 }), 5, 1)).toMatchObject({
    limit: 0,
  });
  expect(accessDenial(row({ status: "rejected" }), 5, 1)).toEqual({
    error: "Your access is pending approval.",
  });
});

test("an approved user under the cap may run", () => {
  expect(accessDenial(row({ reports_count: 4 }), 5)).toBeNull();
  expect(accessDenial(row({ reports_count: null }), 5)).toBeNull();
});

test("the cap is the per-user override, else the default", () => {
  expect(accessDenial(row({ reports_count: 5 }), 5)).toEqual({
    error: "You've used all 5 of your reports. Ask an admin to reset your counter.",
    used: 5,
    limit: 5,
  });
  expect(accessDenial(row({ reports_count: 5, report_limit_override: 10 }), 5)).toBeNull();
  expect(accessDenial(row({ reports_count: 0, report_limit_override: 0 }), 5)).toMatchObject({
    used: 0,
    limit: 0,
  });
});
