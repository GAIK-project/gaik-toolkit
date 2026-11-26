import { expect, test } from "bun:test";
import { maskEmail, signInErrorMessage } from "./sign-in-errors";

test("a banned account is told it expired, not that the password is wrong", () => {
  expect(signInErrorMessage("user_banned")).toContain("expired");
  expect(signInErrorMessage("user_banned")).not.toContain("password");
});

test("wrong credentials and unknown codes keep the generic message", () => {
  expect(signInErrorMessage("invalid_credentials")).toBe(
    "Invalid email or password.",
  );
  expect(signInErrorMessage(undefined)).toBe("Invalid email or password.");
});

test("an unconfirmed address is asked to confirm it", () => {
  expect(signInErrorMessage("email_not_confirmed")).toContain("Confirm");
});

test("the masked address keeps two letters and the domain", () => {
  expect(maskEmail("gaik-testi-1911@example.com")).toBe("ga***@example.com");
  expect(maskEmail("a@gaik.fi")).toBe("a***@gaik.fi");
});

test("an address without a local part masks to nothing readable", () => {
  expect(maskEmail("@example.com")).toBe("***");
  expect(maskEmail("not-an-email")).toBe("***");
});
