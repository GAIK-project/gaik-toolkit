import { expect, test } from "bun:test";
import { existsSync } from "node:fs";
import { join } from "node:path";
import {
  accountOf,
  AVATAR_COUNT,
  avatarIndex,
  initials,
  statusLine,
  type AccountSource,
} from "./account";

// avatarIndex of the two ids pinned in the first test.
const PINNED = [3, 1];

const signedIn = (over: Partial<AccountSource> = {}): AccountSource => ({
  user: {
    id: "5f1c2a9e-0b7d-4c1e-9a3f-2d8e6b4c1a70",
    email: "ava@example.com",
    user_metadata: { full_name: "Ava Johnson" },
  },
  isUnlocked: false,
  isTrial: false,
  emailUnconfirmed: false,
  bypassAuth: false,
  ...over,
});

test("a user keeps the same avatar, and every avatar is one that exists", () => {
  const id = "5f1c2a9e-0b7d-4c1e-9a3f-2d8e6b4c1a70";
  expect(avatarIndex(id)).toBe(avatarIndex(id));
  const seen = new Set<number>();
  for (let n = 0; n < 500; n++) {
    const index = avatarIndex(`user-${n}`);
    expect(index).toBeGreaterThanOrEqual(1);
    expect(index).toBeLessThanOrEqual(AVATAR_COUNT);
    seen.add(index);
  }
  expect(seen.size).toBe(AVATAR_COUNT);
  // Pinned, so a change to the hash or the count, which gives most users
  // another avatar, is made on purpose (docs/avatars.md).
  expect(avatarIndex("5f1c2a9e-0b7d-4c1e-9a3f-2d8e6b4c1a70")).toBe(PINNED[0]);
  expect(avatarIndex("00000000-0000-0000-0000-000000000000")).toBe(PINNED[1]);
  for (let index = 1; index <= AVATAR_COUNT; index++) {
    const file = join(
      import.meta.dir,
      "..",
      "public",
      "avatars",
      `avatar-${index}.webp`,
    );
    expect(existsSync(file)).toBe(true);
  }
});

test("initials come from the first and last name, or the e-mail address", () => {
  expect(initials("Ava Johnson")).toBe("AJ");
  expect(initials("ava maria johnson")).toBe("AJ");
  expect(initials("Ava")).toBe("A");
  expect(initials("ava.johnson@example.com")).toBe("AJ");
  expect(initials("")).toBe("?");
});

test("nobody signed in has no account", () => {
  expect(accountOf(signedIn({ user: null }), 30)).toBeNull();
});

test("the account says what the user can run", () => {
  expect(accountOf(signedIn({ isUnlocked: true }), 30)?.status).toBe("full");
  const trial = accountOf(signedIn({ isTrial: true }), 30)!;
  expect(trial.status).toBe("trial");
  expect(statusLine(trial)).toBe("Trial: 30 demo runs a day");
  expect(accountOf(signedIn({ emailUnconfirmed: true }), 30)?.status).toBe(
    "unconfirmed",
  );
  expect(accountOf(signedIn(), 30)?.status).toBe("pending");
  const declined = accountOf(signedIn({ requestStatus: "rejected" }), 30)!;
  expect(declined.status).toBe("rejected");
  expect(statusLine(declined)).toBe("Your access request was declined");
  // Sign-up's insert of the request failed: nothing waits for approval.
  const missing = accountOf(signedIn({ requestStatus: null }), 30)!;
  expect(missing.status).toBe("norequest");
  expect(statusLine(missing)).toBe("No access request on file");
  const approved = accountOf(
    signedIn({ isUnlocked: true, requestStatus: "approved" }),
    30,
  )!;
  expect(statusLine(approved)).toBe("Account approved");
});

test("the name falls back to the e-mail address", () => {
  const account = accountOf(
    signedIn({
      user: { id: "x", email: "ava@example.com", user_metadata: {} },
    }),
    30,
  )!;
  expect(account.name).toBe("ava@example.com");
  expect(account.email).toBe("ava@example.com");
});

test("local development without sign-in gets a stand-in account", () => {
  const account = accountOf(signedIn({ user: null, bypassAuth: true }), 30)!;
  expect(account.status).toBe("bypass");
  expect(account.email).toBeNull();
});
