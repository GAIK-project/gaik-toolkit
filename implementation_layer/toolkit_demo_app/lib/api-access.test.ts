import { expect, test } from "bun:test";
import {
  EMAIL_UNCONFIRMED,
  type GateState,
  PENDING_DENIAL,
  SHARED_DATA_DENIAL,
  accessRefusal,
  handsOutStorageLink,
  isEmailConfirmed,
  isStateChanging,
  isWizardApiPath,
  needsApprovedUser,
  wizardRefusal,
  writesSharedData,
  namesItsUser,
} from "./api-access";

const NON_READS = ["POST", "PUT", "PATCH", "DELETE", "delete"];

const signedIn: GateState = {
  loggedIn: true,
  approved: false,
  pending: false,
  emailConfirmed: true,
  userId: "u1",
};

test("the wizard API is /api/wizard and the paths under it", () => {
  expect(isWizardApiPath("/api/wizard")).toBe(true);
  expect(isWizardApiPath("/api/wizard/files/s1/poc/run_poc.py")).toBe(true);
  expect(isWizardApiPath("/api/wizardry/start")).toBe(false);
  expect(isWizardApiPath("/api/extract")).toBe(false);
});

test("the wizard needs a signed-in user with the grant", () => {
  expect(wizardRefusal({ loggedIn: false, wizardAccess: false })?.status).toBe(
    401,
  );
  expect(wizardRefusal({ loggedIn: true, wizardAccess: false })?.status).toBe(
    403,
  );
  expect(wizardRefusal({ loggedIn: true, wizardAccess: true })).toBeNull();
});

test("a write to the shared video index passes only a signed-in administrator", async () => {
  // With trial runs left, an approved or pending user without the admin
  // session is refused; the admin session alone does not stand in for sign-in.
  const path = "/api/video-search/clear";
  const trialLeft = async () => ({ ok: true as const });
  for (const method of NON_READS) {
    expect(needsApprovedUser(method)).toBe(true);
    const sharedData = writesSharedData(method, path);
    const refusal = (state: GateState, admin = false) =>
      accessRefusal(state, trialLeft, { sharedData, admin });
    expect(await refusal({ ...signedIn, approved: true }, true)).toBeNull();
    expect(await refusal({ ...signedIn, approved: true })).toEqual(
      SHARED_DATA_DENIAL,
    );
    expect(await refusal({ ...signedIn, pending: true })).toEqual(
      SHARED_DATA_DENIAL,
    );
    expect(await refusal(signedIn)).toEqual(SHARED_DATA_DENIAL);
    expect(
      await refusal({ ...signedIn, loggedIn: false, userId: null }, true),
    ).toEqual({ status: 401, error: "Sign in to use this feature." });
  }
});

test("a video's playback and thumbnail links are told apart from the open reads", () => {
  for (const kind of ["play", "thumbnail"]) {
    const path = `/api/video-search/videos/v1/${kind}`;
    expect(handsOutStorageLink("GET", path)).toBe(true);
    expect(handsOutStorageLink("HEAD", path)).toBe(true);
  }
  for (const path of [
    "/api/video-search/videos",
    "/api/video-search/status",
    "/api/video-search/search",
  ]) {
    expect(handsOutStorageLink("GET", path)).toBe(false);
  }
});

test("elsewhere a non-read method needs an account, and a pending one runs on the trial", async () => {
  const path = "/api/extract";
  const trialLeft = async () => ({ ok: true as const });
  for (const method of NON_READS) {
    expect(needsApprovedUser(method)).toBe(true);
    expect(writesSharedData(method, path)).toBe(false);
  }
  expect(
    await accessRefusal({ ...signedIn, pending: true }, trialLeft),
  ).toBeNull();
});

test("writes to the shared video index are told apart from its search", () => {
  for (const path of [
    "/api/video-search/clear",
    "/api/video-search/clear/",
    "/api/video-search/ingest",
    "/api/video-search/ingest/stream",
  ]) {
    expect(writesSharedData("POST", path)).toBe(true);
    expect(writesSharedData("GET", path)).toBe(false);
  }
  for (const path of [
    "/api/video-search/search",
    "/api/video-search/clearance",
    "/api/video-search/ingested",
  ]) {
    expect(writesSharedData("POST", path)).toBe(false);
  }
});

test("reads pass through to the backend", () => {
  for (const method of ["GET", "HEAD", "OPTIONS"]) {
    expect(needsApprovedUser(method)).toBe(false);
    expect(isStateChanging(method)).toBe(false);
  }
});

test("a request with the user's own model key still needs an account", async () => {
  const take = async () => {
    throw new Error("an own-key run must not spend a trial run");
  };
  const ownKey = { ownModelKey: true };
  expect(
    await accessRefusal(
      {
        loggedIn: false,
        approved: false,
        pending: false,
        emailConfirmed: false,
        userId: null,
      },
      take,
      ownKey,
    ),
  ).toEqual({ status: 401, error: "Sign in to use this feature." });
  expect(
    await accessRefusal(
      {
        loggedIn: true,
        approved: false,
        pending: true,
        emailConfirmed: true,
        userId: "u1",
      },
      take,
      ownKey,
    ),
  ).toBeNull();
  expect(
    await accessRefusal(
      {
        loggedIn: true,
        approved: false,
        pending: false,
        emailConfirmed: true,
        userId: "u1",
      },
      take,
      ownKey,
    ),
  ).toEqual(PENDING_DENIAL);
});

test("an own model key does not open a write to shared data", async () => {
  const take = async () => {
    throw new Error("a shared-data write must not spend a trial run");
  };
  expect(
    await accessRefusal({ ...signedIn, pending: true }, take, {
      ownModelKey: true,
      sharedData: true,
    }),
  ).toEqual(SHARED_DATA_DENIAL);
});

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

test("a pending user without a confirmed e-mail address runs neither a trial run nor their own key", async () => {
  const take = async () => {
    throw new Error("the trial must not be touched");
  };
  const unconfirmed = { ...signedIn, pending: true, emailConfirmed: false };
  expect(await accessRefusal(unconfirmed, take)).toEqual(EMAIL_UNCONFIRMED);
  expect(await accessRefusal(unconfirmed, take, { ownModelKey: true })).toEqual(
    EMAIL_UNCONFIRMED,
  );
  // A request that is no demo run, such as ending a wizard session, needs no
  // confirmed address.
  expect(
    await accessRefusal(unconfirmed, take, { noTrialRun: true }),
  ).toBeNull();
  // An approved user's run does not depend on it.
  expect(
    await accessRefusal(
      { ...unconfirmed, pending: false, approved: true },
      take,
    ),
  ).toBeNull();
});

test("an e-mail address counts as confirmed only with a confirmation time", () => {
  expect(isEmailConfirmed({ email_confirmed_at: "2026-01-01T00:00:00Z" })).toBe(
    true,
  );
  expect(isEmailConfirmed({ email_confirmed_at: null })).toBe(false);
  expect(isEmailConfirmed({})).toBe(false);
  expect(isEmailConfirmed(null)).toBe(false);
});


test("only runs and result downloads name their user", () => {
  expect(namesItsUser("POST", "/api/pipeline/document")).toBe(true);
  expect(namesItsUser("DELETE", "/api/tabular-agent/session/abc")).toBe(true);
  expect(namesItsUser("GET", "/api/pipeline/pdf/abc")).toBe(true);
  expect(namesItsUser("GET", "/api/diary/pdf/abc")).toBe(true);
  expect(namesItsUser("GET", "/api/luvata-order/pdf/abc")).toBe(true);
  expect(namesItsUser("GET", "/api/dental-transcribe/srt/abc")).toBe(true);
  expect(namesItsUser("GET", "/api/dental-transcribe/vtt/abc")).toBe(true);
  expect(namesItsUser("GET", "/api/rag/status/abc")).toBe(true);
  expect(namesItsUser("GET", "/api/video-search/videos/abc/thumbnail")).toBe(false);
  expect(namesItsUser("GET", "/api/tabular-agent/status")).toBe(false);
  expect(namesItsUser("GET", "/api/pipeline/pdf/abc/extra")).toBe(false);
});
