import { expect, test } from "bun:test";
import { accessDenial, clientIp } from "./gate";

const row = (over: object = {}) => ({
  status: "approved",
  reports_count: 0,
  report_limit_override: null,
  ...over,
});

test("clientIp takes the first x-forwarded-for hop, then x-real-ip", () => {
  expect(clientIp(new Headers({ "x-forwarded-for": " 1.2.3.4 , 5.6.7.8" }))).toBe("1.2.3.4");
  expect(clientIp(new Headers({ "x-real-ip": "9.9.9.9" }))).toBe("9.9.9.9");
  expect(clientIp(new Headers())).toBe("anonymous");
});

test("a missing or unapproved row is pending approval", () => {
  const pending = { error: "Your access is pending approval." };
  expect(accessDenial(null, 5)).toEqual(pending);
  expect(accessDenial(row({ status: "pending" }), 5)).toEqual(pending);
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
