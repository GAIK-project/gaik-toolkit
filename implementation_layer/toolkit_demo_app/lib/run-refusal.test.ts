import { describe, expect, test } from "bun:test";
import type { ModelUse } from "./model-use";
import {
  accessNoticeText,
  heldOwnKeyUse,
  ownKeyHeldText,
  runBlockedLabel,
  runRefusal,
} from "./run-refusal";

describe("runRefusal", () => {
  test("a visitor who is not signed in is asked to sign in", () => {
    expect(runRefusal({ loggedIn: false, emailUnconfirmed: false })).toBe(
      "sign-in",
    );
  });

  test("a pending user with an unconfirmed e-mail address is asked to confirm it", () => {
    expect(runRefusal({ loggedIn: true, emailUnconfirmed: true })).toBe(
      "confirm-email",
    );
  });

  test("a signed-in user with a confirmed address waits for approval", () => {
    expect(runRefusal({ loggedIn: true, emailUnconfirmed: false })).toBe(
      "approval",
    );
  });
});

describe("the texts for an unconfirmed e-mail address", () => {
  test("the access notice names the confirmation, not the approval", () => {
    const text = accessNoticeText("confirm-email");
    expect(text).toContain("Confirm your e-mail address");
    expect(text).not.toContain("pending approval");
  });

  test("the run button names the confirmation, not the approval", () => {
    const label = runBlockedLabel("confirm-email");
    expect(label).toContain("Confirm your e-mail");
    expect(label).not.toContain("approval");
  });

  test("the other reasons keep their texts", () => {
    expect(accessNoticeText("sign-in")).toBe("Sign in to run this demo.");
    expect(accessNoticeText("approval")).toContain("pending approval");
    expect(runBlockedLabel("sign-in")).toBe("Sign in to run");
    expect(runBlockedLabel("approval")).toBe("Waiting for approval");
  });
});

describe("heldOwnKeyUse", () => {
  const running: ModelUse = {
    runsHere: true,
    summary: "Your own model runs this demo: gpt-6-luna.",
    details: ["Recordings are transcribed on the server first."],
    problem: null,
  };

  test("a saved own key whose runs are refused is not named as the running model", () => {
    const use = heldOwnKeyUse(running, true, "confirm-email");
    expect(use.runsHere).toBe(false);
    expect(use.summary).toBe(ownKeyHeldText("confirm-email"));
    expect(use.summary).not.toContain("runs this demo");
    expect(use.details).toEqual([]);
  });

  test("each reason says what opens the key's runs", () => {
    expect(ownKeyHeldText("sign-in")).toContain("sign in");
    expect(ownKeyHeldText("confirm-email")).toContain(
      "confirm your e-mail address",
    );
    expect(ownKeyHeldText("approval")).toContain("approved");
  });

  test("an own key whose runs are open keeps its notice", () => {
    expect(heldOwnKeyUse(running, true, null)).toBe(running);
  });

  test("a picked server model keeps its notice", () => {
    const server = { ...running, summary: "Gemma 4 31B runs this demo." };
    expect(heldOwnKeyUse(server, false, "approval")).toBe(server);
  });
});
