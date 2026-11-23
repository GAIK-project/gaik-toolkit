import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { caseChatReference, keepChatReference, takeChatReference } from "./case-chat";
import { CASE_STRINGS } from "./case-strings";

const fi = CASE_STRINGS.fi.chat;
const en = CASE_STRINGS.en.chat;
const SESSION = "2fa204b7";

describe("caseChatReference", () => {
  it("names the open case and its status", () => {
    const ref = caseChatReference(SESSION, { number: 13, status: "Odottaa hyväksyntää" }, fi);

    expect(ref.key).toBe(`cases:${SESSION}`);
    expect(ref.label).toBe("Tapaus 13");
    expect(ref.prefix).toContain("tapauksella 13");
    expect(ref.prefix).toContain("Odottaa hyväksyntää");
    expect(caseChatReference(SESSION, { number: 2, status: "Awaiting approval" }, en).label).toBe("Case 2");
  });

  it("quotes a failed run's message on one line", () => {
    const ref = caseChatReference(
      SESSION,
      { number: 4, status: "Ajo epäonnistui", failure: 'Traceback:\n  KeyError: "urgency"' },
      fi,
    );

    expect(ref.prefix).toContain("Traceback: KeyError: 'urgency'");
    expect(ref.prefix).not.toContain("\n");
  });

  it("quotes the reviewer's comment of a returned case on one line", () => {
    const ref = caseChatReference(
      SESSION,
      { number: 7, status: "Palautettu", comment: 'Kenttä "halli" puuttuu.\nLisää se tulokseen.' },
      fi,
    );

    expect(ref.label).toBe("Tapaus 7");
    expect(ref.prefix).toContain("tapauksella 7");
    expect(ref.prefix).toContain("palautettiin korjattavaksi");
    expect(ref.prefix).toContain("Kenttä 'halli' puuttuu. Lisää se tulokseen.");
    expect(ref.prefix).not.toContain("\n");
    const english = caseChatReference(SESSION, { number: 7, status: "Returned", comment: "Add the hall." }, en);
    expect(english.prefix).toContain(`the reviewer's comment quoted: "Add the hall."`);
  });

  it("says a case run again in its own words, by the flag and not the comment's text", () => {
    const again = caseChatReference(SESSION, { number: 7, status: "x", comment: "Kokeilen toista tallennetta.", rerun: true }, fi);
    const returned = caseChatReference(SESSION, { number: 7, status: "x", comment: "Ajetaan uudelleen." }, fi);

    expect(again.prefix).toContain("tapaus ajetaan uudelleen");
    expect(again.prefix).toContain('"Kokeilen toista tallennetta."');
    expect(again.prefix).not.toContain("palautettiin korjattavaksi");
    // The same words from a reviewer are a return.
    expect(returned.prefix).toContain("palautettiin korjattavaksi");
  });

  it("cuts a long comment and keeps the plain line for a blank one", () => {
    const long = caseChatReference(SESSION, { number: 7, status: "Palautettu", comment: "x".repeat(2000) }, fi);
    const blank = caseChatReference(SESSION, { number: 7, status: "Palautettu", comment: "  " }, fi);

    expect(long.prefix.length).toBeLessThan(500);
    expect(long.prefix).toContain("…");
    expect(blank.prefix).toContain("(tila: Palautettu)");
  });

  it("names the failed run before an earlier return's comment", () => {
    // A returned case that was sent again and failed still carries the comment.
    const ref = caseChatReference(
      SESSION,
      { number: 7, status: "Ajo epäonnistui", failure: "KeyError: 'hall'", comment: "Lisää halli." },
      fi,
    );

    expect(ref.prefix).toContain("ajo epäonnistui");
    expect(ref.prefix).not.toContain("Lisää halli.");
  });

  it("speaks of the cases in general when none is open", () => {
    const ref = caseChatReference(SESSION, null, fi);

    expect(ref.label).toBe(fi.labelNone);
    expect(ref.prefix).toBe(fi.prefixNone);
  });
});

describe("the reference kept for the session page", () => {
  const store = new Map<string, string>();
  beforeEach(() => {
    store.clear();
    vi.stubGlobal("window", {
      sessionStorage: {
        getItem: (k: string) => store.get(k) ?? null,
        setItem: (k: string, v: string) => void store.set(k, v),
        removeItem: (k: string) => void store.delete(k),
      },
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("is taken once, by the session it was kept for", () => {
    const ref = caseChatReference(SESSION, { number: 13, status: "Palautettu" }, fi);

    expect(keepChatReference(SESSION, ref)).toBe(true);
    expect(takeChatReference("another-session")).toBeNull();
    expect(takeChatReference(SESSION)).toEqual(ref);
    expect(takeChatReference(SESSION)).toBeNull();
  });

  it("takes nothing that is not a reference", () => {
    store.set(`gaik-wizard:pending-chat-reference:${SESSION}`, '{"label": 5}');

    expect(takeChatReference(SESSION)).toBeNull();
    expect(store.size).toBe(0);
  });

  it("says so when storage is blocked", () => {
    vi.stubGlobal("window", {
      get sessionStorage(): Storage {
        throw new Error("blocked");
      },
    });

    expect(keepChatReference(SESSION, caseChatReference(SESSION, null, fi))).toBe(false);
    expect(takeChatReference(SESSION)).toBeNull();
  });
});
