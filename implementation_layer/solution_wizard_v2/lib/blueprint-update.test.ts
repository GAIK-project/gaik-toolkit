import { describe, expect, it, vi } from "vitest";

// lib/i18n reads the locale cookie through next/headers, which only exists inside Next.
vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => undefined }) }));

import {
  blueprintUpdateText,
  chatActivityAtLoad,
  chatReplyingChanged,
  knownVersion,
  pageReadSession,
} from "@/lib/blueprint-update";
import { dictionary } from "@/lib/i18n";

const fi = dictionary("fi");
const en = dictionary("en");

// A customer reviewer could not tell whether the Workflow tab's diagram showed
// what the chat had just changed: the diagram was drawn again without a word.
// These pin what the status line says then, and when it may say "from the chat".

describe("blueprintUpdateText", () => {
  it("names the chat and the blueprint version, in both languages", () => {
    expect(blueprintUpdateText({ version: 7, fromChat: true }, fi)).toBe(
      "Päivitetty chatista · blueprintin versio 7",
    );
    expect(blueprintUpdateText({ version: 7, fromChat: true }, en)).toBe(
      "Updated from the chat · blueprint version 7",
    );
  });

  it("does not name the chat for a version written elsewhere", () => {
    expect(blueprintUpdateText({ version: 3, fromChat: false }, fi)).toBe(
      "Päivitetty uusimpaan versioon · blueprintin versio 3",
    );
    expect(blueprintUpdateText({ version: 3, fromChat: false }, en)).not.toContain("chat");
  });

  it("leaves the version out when it is not known, rather than showing a default", () => {
    expect(blueprintUpdateText({ version: null, fromChat: true }, fi)).toBe("Päivitetty chatista");
  });
});

describe("knownVersion", () => {
  it("takes the session's own version number", () => {
    expect(knownVersion(1)).toBe(1);
    expect(knownVersion(12)).toBe(12);
  });

  it("is null for anything that is not one", () => {
    for (const value of [0, -1, 1.5, Number.NaN, "3", null, undefined]) {
      expect(knownVersion(value)).toBeNull();
    }
  });
});

describe("which blueprint is the chat's", () => {
  it("one the page reads when a reply has ended", () => {
    let activity = chatActivityAtLoad(false);
    activity = chatReplyingChanged(activity, true);
    activity = chatReplyingChanged(activity, false);
    expect(pageReadSession(activity).fromChat).toBe(true);
  });

  it("one the page reads in the middle of a reply, and the one after the reply too", () => {
    let activity = chatReplyingChanged(chatActivityAtLoad(false), true);
    const mid = pageReadSession(activity);
    expect(mid.fromChat).toBe(true);
    activity = chatReplyingChanged(mid.next, false);
    expect(pageReadSession(activity).fromChat).toBe(true);
  });

  it("one read while a reply the page was loaded into is still on its way", () => {
    expect(pageReadSession(chatActivityAtLoad(true)).fromChat).toBe(true);
  });

  it("not one read with no reply since the reading before", () => {
    expect(pageReadSession(chatActivityAtLoad(false)).fromChat).toBe(false);

    let activity = chatReplyingChanged(chatActivityAtLoad(false), true);
    activity = chatReplyingChanged(activity, false);
    const afterReply = pageReadSession(activity);
    // The next reading (a save refused for a version written in another window, say) is not the chat's.
    expect(pageReadSession(afterReply.next).fromChat).toBe(false);
  });
});
