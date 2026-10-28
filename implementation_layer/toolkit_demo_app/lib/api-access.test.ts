import { expect, test } from "bun:test";
import {
  PENDING_DENIAL,
  accessRefusal,
  isStateChanging,
  needsApprovedUser,
} from "./api-access";

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

test("a request with the user's own model key needs no account", () => {
  expect(needsApprovedUser("POST", "/api/extract", true)).toBe(false);
  expect(needsApprovedUser("POST", "/api/extract", false)).toBe(true);
  expect(needsApprovedUser("DELETE", "/api/video-search/clear", false)).toBe(
    true,
  );
});

const signedIn = {
  loggedIn: true,
  approved: false,
  pending: false,
  userId: "u1",
};

test("an approved user runs without spending a trial run", async () => {
  const calls: string[] = [];
  const take = async (id: string) => {
    calls.push(id);
    return { ok: true as const };
  };
  expect(await accessRefusal({ ...signedIn, approved: true }, take)).toBeNull();
  expect(calls).toEqual([]);
});

test("a pending user runs on the trial allowance until it is used up", async () => {
  const calls: string[] = [];
  const ok = async (id: string) => {
    calls.push(id);
    return { ok: true as const };
  };
  expect(await accessRefusal({ ...signedIn, pending: true }, ok)).toBeNull();
  expect(calls).toEqual(["u1"]);

  const spent = async () => ({
    ok: false as const,
    status: 429,
    error: "You've used today's 30 trial runs.",
  });
  expect(await accessRefusal({ ...signedIn, pending: true }, spent)).toEqual({
    status: 429,
    error: "You've used today's 30 trial runs.",
  });
});

test("a rejected or unknown user and a visitor are refused", async () => {
  const take = async () => {
    throw new Error("the trial must not be touched");
  };
  expect(await accessRefusal(signedIn, take)).toEqual(PENDING_DENIAL);
  expect(
    await accessRefusal({ ...signedIn, pending: true, userId: null }, take),
  ).toEqual(PENDING_DENIAL);
  expect(
    await accessRefusal({ ...signedIn, loggedIn: false, userId: null }, take),
  ).toEqual({ status: 401, error: "Sign in to use this feature." });
});
