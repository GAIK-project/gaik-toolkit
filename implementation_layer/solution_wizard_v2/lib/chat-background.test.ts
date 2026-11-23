import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  BACKGROUNDS,
  BACKGROUND_KEY,
  BACKGROUND_SENTENCES,
  DEFAULT_PACE,
  PACES,
  PACE_KEY,
  PACE_SENTENCES,
  START_LINES_ROOM,
  isBackground,
  isPace,
  onBackgroundChange,
  onPaceChange,
  saveBackground,
  savePace,
  savedBackground,
  savedPace,
  withStartLines,
  withoutStartLines,
} from "./chat-background";

const fi = BACKGROUND_SENTENCES.fi;
const en = BACKGROUND_SENTENCES.en;
const paceFi = PACE_SENTENCES.fi;
const paceEn = PACE_SENTENCES.en;
const LOCALES = ["fi", "en"] as const;

describe("the choices' lines of a first message", () => {
  it("go on lines of their own before what the user wrote, the background first", () => {
    expect(withStartLines("Haluan luokitella laskut.", [fi.technical, paceFi.quick])).toBe(
      `${fi.technical}\n${paceFi.quick}\nHaluan luokitella laskut.`,
    );
    expect(withStartLines("  Sort our invoices.  ", [en.nonTechnical, paceEn.thorough])).toBe(
      `${en.nonTechnical}\n${paceEn.thorough}\nSort our invoices.`,
    );
  });

  it("leave out a choice that was not made", () => {
    // No background chosen: the pace line alone.
    expect(withStartLines("Haluan luokitella laskut.", [null, paceFi.quick])).toBe(
      `${paceFi.quick}\nHaluan luokitella laskut.`,
    );
    expect(withStartLines("Haluan luokitella laskut.", [null, undefined, "  "])).toBe(
      "Haluan luokitella laskut.",
    );
    expect(withStartLines("Haluan luokitella laskut.", [])).toBe("Haluan luokitella laskut.");
  });

  it("are never sent alone", () => {
    expect(withStartLines("", [fi.technical, paceFi.quick])).toBe("");
    expect(withStartLines("  \n ", [fi.technical, paceFi.quick])).toBe("  \n ");
  });

  it("fit in the room kept for them in the message field", () => {
    for (const locale of LOCALES) {
      for (const b of BACKGROUNDS) {
        for (const p of PACES) {
          const whole = withStartLines("x", [BACKGROUND_SENTENCES[locale][b], PACE_SENTENCES[locale][p]]);
          expect(whole.length - 1).toBeLessThanOrEqual(START_LINES_ROOM);
        }
      }
    }
  });

  it("say what the owner asked the wizard to be told about the pace", () => {
    expect(paceEn.quick).toBe(
      "Pace: quick. Ask only what you cannot reasonably assume, in one round if you can; propose defaults for the rest and list them as assumptions.",
    );
    expect(paceEn.thorough).toBe("Pace: thorough. Ask what you need to get the details right.");
    expect(paceFi.quick).toBe(
      "Tahti: nopea. Kysy vain se, mitä et voi kohtuudella olettaa, mieluiten yhdellä kierroksella; ehdota muuhun oletukset ja listaa ne oletuksina.",
    );
    expect(paceFi.thorough).toBe(
      "Tahti: perusteellinen. Kysy se, mitä tarvitset yksityiskohtien saamiseksi oikein.",
    );
  });
});

describe("a user's message as it is shown", () => {
  it("leaves out the lines it was sent with, for every choice in either language", () => {
    for (const locale of LOCALES) {
      for (const b of [...BACKGROUNDS, null]) {
        for (const p of PACES) {
          const lines = [b ? BACKGROUND_SENTENCES[locale][b] : null, PACE_SENTENCES[locale][p]];
          expect(withoutStartLines(withStartLines("Luokittele laskut.", lines))).toBe("Luokittele laskut.");
        }
      }
    }
  });

  it("leaves out a background line sent without a pace line", () => {
    expect(withoutStartLines(withStartLines("Luokittele laskut.", [en.technical]))).toBe(
      "Luokittele laskut.",
    );
  });

  it("reads a session from the time the sentence stood in the field, on the same line", () => {
    expect(withoutStartLines(`${fi.nonTechnical} Luokittele saapuvat sähköpostit`)).toBe(
      "Luokittele saapuvat sähköpostit",
    );
    expect(withoutStartLines(`${en.technical} We sort e-mails by hand.`)).toBe("We sort e-mails by hand.");
  });

  it("keeps the user's own lines after them as they wrote them", () => {
    expect(withoutStartLines(`${fi.technical}\n${paceFi.thorough}\nEnsimmäinen rivi.\n\nToinen rivi.`)).toBe(
      "Ensimmäinen rivi.\n\nToinen rivi.",
    );
  });

  it("leaves a message that does not start with them as it is", () => {
    expect(withoutStartLines("Luokittele laskut.")).toBe("Luokittele laskut.");
    expect(withoutStartLines(`Laskut. ${fi.technical}`)).toBe(`Laskut. ${fi.technical}`);
    expect(withoutStartLines(`Laskut.\n${paceFi.quick}`)).toBe(`Laskut.\n${paceFi.quick}`);
    // The start of a sentence alone is the user's own words.
    expect(withoutStartLines("Taustani: olen tekninen. Laskut.")).toBe("Taustani: olen tekninen. Laskut.");
    expect(withoutStartLines("Tahti: nopea. Laskut.")).toBe("Tahti: nopea. Laskut.");
    expect(withoutStartLines("  Laskut.\n")).toBe("  Laskut.\n");
  });

  it("takes out one line of each choice, in the order they are sent", () => {
    // A pace line the user wrote after the lines is theirs.
    expect(withoutStartLines(`${paceEn.quick}\n${paceEn.quick}`)).toBe(paceEn.quick);
    expect(withoutStartLines(`${paceEn.quick}\n${en.technical}\nInvoices.`)).toBe(`${en.technical}\nInvoices.`);
  });

  it("leaves nothing of a message that was the lines alone", () => {
    expect(withoutStartLines(en.technical)).toBe("");
    expect(withoutStartLines(`${fi.nonTechnical}\n${paceFi.quick} `)).toBe("");
  });
});

describe("the remembered choices", () => {
  const store = new Map<string, string>();
  let blocked = false;
  const listeners = new Set<() => void>();
  beforeEach(() => {
    store.clear();
    blocked = false;
    const guard = <T>(run: () => T): T => {
      if (blocked) throw new Error("storage blocked");
      return run();
    };
    vi.stubGlobal("window", {
      localStorage: {
        getItem: (k: string) => guard(() => store.get(k) ?? null),
        setItem: (k: string, v: string) => guard(() => void store.set(k, v)),
        removeItem: (k: string) => guard(() => void store.delete(k)),
      },
      addEventListener: (_name: string, listener: () => void) => void listeners.add(listener),
      removeEventListener: (_name: string, listener: () => void) => void listeners.delete(listener),
    });
  });
  afterEach(() => {
    // Nothing is held in memory for the next test.
    blocked = false;
    saveBackground(null);
    savePace(null);
    listeners.clear();
    vi.unstubAllGlobals();
  });

  it("the background is remembered in this browser, and forgotten when it is taken back", () => {
    expect(savedBackground()).toBeNull();
    saveBackground("technical");
    expect(store.get(BACKGROUND_KEY)).toBe("technical");
    expect(savedBackground()).toBe("technical");
    saveBackground("nonTechnical");
    expect(savedBackground()).toBe("nonTechnical");
    saveBackground(null);
    expect(store.has(BACKGROUND_KEY)).toBe(false);
    expect(savedBackground()).toBeNull();
  });

  it("the pace is quick until the user chooses, and is remembered apart from the background", () => {
    expect(DEFAULT_PACE).toBe("quick");
    expect(savedPace()).toBe("quick");
    savePace("thorough");
    expect(store.get(PACE_KEY)).toBe("thorough");
    expect(savedPace()).toBe("thorough");
    expect(savedBackground()).toBeNull();
    savePace("quick");
    expect(savedPace()).toBe("quick");
  });

  it("reads only a known choice back from storage", () => {
    store.set(BACKGROUND_KEY, "admin");
    store.set(PACE_KEY, "slow");
    expect(savedBackground()).toBeNull();
    expect(savedPace()).toBe("quick");
    expect(isBackground("technical")).toBe(true);
    expect(isBackground("quick")).toBe(false);
    expect(isBackground(null)).toBe(false);
    expect(isPace("thorough")).toBe(true);
    expect(isPace("technical")).toBe(false);
  });

  it("stand for this page when the browser blocks storage", () => {
    blocked = true;
    expect(savedBackground()).toBeNull();
    saveBackground("technical");
    savePace("thorough");
    expect(savedBackground()).toBe("technical");
    expect(savedPace()).toBe("thorough");
    saveBackground(null);
    expect(savedBackground()).toBeNull();
  });

  it("tell a view that shows them when they change, here or in another tab", () => {
    const background = vi.fn();
    const pace = vi.fn();
    const stopBackground = onBackgroundChange(background);
    const stopPace = onPaceChange(pace);
    saveBackground("technical");
    expect(background).toHaveBeenCalledTimes(1);
    expect(pace).not.toHaveBeenCalled();
    savePace("thorough");
    expect(pace).toHaveBeenCalledTimes(1);
    // Another tab's change arrives as the browser's storage event.
    for (const listener of [...listeners]) listener();
    expect(background).toHaveBeenCalledTimes(2);
    expect(pace).toHaveBeenCalledTimes(2);
    stopBackground();
    stopPace();
    saveBackground(null);
    savePace(null);
    expect(background).toHaveBeenCalledTimes(2);
    expect(pace).toHaveBeenCalledTimes(2);
    expect(listeners.size).toBe(0);
  });
});
