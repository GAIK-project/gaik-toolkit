import { expect, test } from "bun:test";
import { maskEmail, signInErrorMessage } from "./sign-in-errors";

test("a banned account is told it expired, not that the password is wrong", () => {
  expect(signInErrorMessage("user_banned", 400)).toContain("expired");
  expect(signInErrorMessage("user_banned", 400)).not.toContain("password");
});

test("wrong credentials and unknown 4xx codes keep the generic message", () => {
  expect(signInErrorMessage("invalid_credentials", 400)).toBe(
    "Invalid email or password.",
  );
  expect(signInErrorMessage("something_new", 422)).toBe(
    "Invalid email or password.",
  );
});

test("an unconfirmed address is asked to confirm it", () => {
  expect(signInErrorMessage("email_not_confirmed", 400)).toContain("Confirm");
});

test("a rate limit asks the user to wait, not to retype the password", () => {
  expect(signInErrorMessage("over_request_rate_limit", 429)).toContain("Wait");
});

test("an outage or network failure is not reported as a wrong password", () => {
  for (const status of [undefined, 0, 500, 503]) {
    expect(signInErrorMessage(undefined, status)).toContain("not available");
  }
  expect(signInErrorMessage("unexpected_failure", 500)).toContain(
    "not available",
  );
});

test("the masked address keeps two letters and the domain", () => {
  expect(maskEmail("gaik-testi-1911@example.com")).toBe("ga***@example.com");
  expect(maskEmail("a@gaik.fi")).toBe("a***@gaik.fi");
});

test("an address without a local part masks to nothing readable", () => {
  expect(maskEmail("@example.com")).toBe("***");
  expect(maskEmail("not-an-email")).toBe("***");
});
