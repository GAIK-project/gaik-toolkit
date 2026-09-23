import { expect, test } from "bun:test";
import { isStateChanging, needsApprovedUser } from "./api-access";

test("every non-read method needs an approved user", () => {
  for (const method of ["POST", "PUT", "PATCH", "DELETE", "delete"]) {
    expect(needsApprovedUser(method, "/api/video-search/clear")).toBe(true);
  }
});

test("reads pass through to the backend", () => {
  for (const method of ["GET", "HEAD", "OPTIONS"]) {
    expect(needsApprovedUser(method, "/api/health")).toBe(false);
    expect(isStateChanging(method)).toBe(false);
  }
});

test("the wizard API keeps its own gate", () => {
  expect(needsApprovedUser("POST", "/api/wizard/start")).toBe(false);
  expect(needsApprovedUser("DELETE", "/api/wizard/end/abc")).toBe(false);
});
