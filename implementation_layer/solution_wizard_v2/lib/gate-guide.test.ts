import { describe, expect, it, vi } from "vitest";

vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => undefined }) }));

import { LOCALES, dictionary } from "@/lib/i18n";
import { gateReference, missingAnswersMessage, nowLine } from "@/lib/gate-guide";
import { buildGateStatus, GATE_STEPS, STEP_COUNT } from "@/lib/wizard-state-machine";

const fi = dictionary("fi");
const en = dictionary("en");

describe("nowLine", () => {
  it("has one line for every step, in both languages", () => {
    for (const loc of LOCALES) {
      const t = dictionary(loc);
      expect(t.nowSteps).toHaveLength(STEP_COUNT);
      for (let step = 1; step <= STEP_COUNT; step++) {
        const line = nowLine(t, step, buildGateStatus(step), false);
        expect(line.length).toBeGreaterThan(10);
        // Every tab placeholder is filled with the tab's own name.
        expect(line).not.toMatch(/\{\w+\}/);
      }
    }
  });

  it("names the workspace tabs by their labels", () => {
    expect(nowLine(fi, 11, buildGateStatus(11), false)).toBe(
      "Tarkista testiajon tulos PoC-välilehdellä. Kerro chatissa, jos jotain pitää muuttaa.",
    );
    expect(nowLine(fi, 8, buildGateStatus(8), false)).toContain("Työnkulku-välilehdellä");
  });

  it("at Gate 3, and on the PoC step before it, follows the test run", () => {
    expect(nowLine(fi, 11, buildGateStatus(11), true)).toMatch(/^Testi onnistui\./);
    expect(nowLine(fi, 10, buildGateStatus(10), true)).toBe(nowLine(fi, 11, buildGateStatus(11), true));
    // No other step changes with a run.
    expect(nowLine(fi, 12, buildGateStatus(12), true)).toBe(nowLine(fi, 12, buildGateStatus(12), false));
  });

  it("names what to check at a gate and leaves the approval to its button", () => {
    for (const loc of LOCALES) {
      const t = dictionary(loc);
      for (const step of GATE_STEPS) {
        for (const ran of [false, true]) {
          // Gate 3 after a run that succeeded: see the next test.
          if (step === GATE_STEPS[2] && ran) continue;
          expect(nowLine(t, step, buildGateStatus(step), ran)).not.toMatch(/hyväksy|approve/i);
        }
      }
    }
  });

  it("after a test run that succeeded names the decision bar's two buttons by their labels without naming a screen edge", () => {
    for (const loc of LOCALES) {
      const t = dictionary(loc);
      const line = nowLine(t, GATE_STEPS[2], buildGateStatus(GATE_STEPS[2]), true);
      expect(line).toContain(t.gateDecisions[2]);
      expect(line).toContain(t.gateRequestChanges);
      expect(line).not.toMatch(/alareunasta|at the bottom/i);
      expect(line).not.toMatch(/\{\w+\}/);
    }
    expect(nowLine(fi, GATE_STEPS[2], buildGateStatus(GATE_STEPS[2]), true)).toBe(
      "Testi onnistui. Tarkista tulos PoC-välilehdellä ja valitse sitten Hyväksy testiajo tai Pyydä muutoksia.",
    );
  });

  it("after a run of a package that changed since asks for a new run and names no approval", () => {
    for (const loc of LOCALES) {
      const t = dictionary(loc);
      const line = nowLine(t, GATE_STEPS[2], buildGateStatus(GATE_STEPS[2]), true, true);
      expect(line).toContain(t.wsTabPoc);
      expect(line).not.toContain(t.gateDecisions[2]);
      expect(line).not.toContain(t.gateRequestChanges);
      expect(line).not.toMatch(/\{\w+\}/);
    }
    expect(nowLine(fi, GATE_STEPS[2], buildGateStatus(GATE_STEPS[2]), true, true)).toBe(
      "PoC-paketti muuttui onnistuneen testiajon jälkeen. Aja testi uudelleen PoC-välilehdellä, niin testiajon voi hyväksyä.",
    );
    // Only Gate 3 waits for the run: an approved last gate is still done.
    const done = { ...buildGateStatus(STEP_COUNT), [STEP_COUNT]: "approved" as const };
    expect(nowLine(fi, STEP_COUNT, done, true, true)).toBe(fi.nowDone);
  });

  it("on an approved gate before the last points onwards instead of asking to check again", () => {
    const approved = { ...buildGateStatus(9), 9: "approved" as const };
    expect(nowLine(fi, 9, approved, false)).toBe("Gate 2 on jo hyväksytty. Jatka seuraavaan vaiheeseen.");
    expect(nowLine(fi, 9, { ...approved, 9: "rejected" }, false)).toBe(nowLine(fi, 9, buildGateStatus(9), false));
  });

  it("says the work is done once Gate 4 is approved", () => {
    const approved = { ...buildGateStatus(STEP_COUNT), [STEP_COUNT]: "approved" as const };
    expect(nowLine(fi, STEP_COUNT, approved, true)).toBe(fi.nowDone);
    // Without a successful run there is no package below to take yet.
    expect(nowLine(fi, STEP_COUNT, approved, false)).toBe(
      "Kaikki gatet on hyväksytty. Aja vielä testi PoC-välilehdellä, niin käyttöönottopaketin voi ladata.",
    );
    // Until then the last step is still a gate to check.
    expect(nowLine(fi, STEP_COUNT, buildGateStatus(STEP_COUNT), true)).toBe(
      "Lataa käyttöönottopaketti PoC-välilehdeltä ja tarkista sen dokumentaatio.",
    );
  });
});

describe("gate copy", () => {
  it("has a topic, a decision, a note and checks for each gate", () => {
    for (const loc of LOCALES) {
      const t = dictionary(loc);
      for (const list of [t.gateTopics, t.gateDecisions, t.gateApproveNotes, t.gateChecks]) {
        expect(list).toHaveLength(GATE_STEPS.length);
      }
      for (const checks of t.gateChecks) {
        expect(checks.length).toBeGreaterThanOrEqual(2);
        expect(checks.length).toBeLessThanOrEqual(3);
      }
    }
  });

  it("uses one word for a gate in the user's copy", () => {
    for (const loc of LOCALES) {
      const text = JSON.stringify(dictionary(loc)).toLowerCase();
      for (const word of ["tarkastuspiste", "gate-vaihe", "checkpoint", "gate step"]) {
        expect(text).not.toContain(word);
      }
    }
  });
});

describe("gateReference", () => {
  const labels = { topics: fi.gateTopics, chip: fi.gateChip, prefix: fi.gateRequestPrefix };

  it("keys the chip by the gate's step and names the gate and its topic", () => {
    expect(gateReference(labels, 2, 9)).toEqual({
      key: "gate:9",
      label: "Gate 2 · Ratkaisun rakenne",
      prefix: "Muutospyyntö ennen Gate 2:n (ratkaisun rakenne) hyväksyntää:",
    });
  });

  it("writes a change to an approved stage", () => {
    const change = gateReference({ ...labels, prefix: fi.gateChangePrefix }, 1, 4);
    expect(change.prefix).toBe("Haluan muuttaa hyväksyttyä vaihetta Gate 1 (vaatimukset):");
  });
});

describe("missingAnswersMessage", () => {
  const entries = [
    { item: fi.bcCurrentProcess, answer: 'Laskut kirjataan käsin.\n\nKenttä "summa" tarkistetaan.', notKnown: false },
    { item: fi.bcExpectedValue, answer: "", notKnown: true },
  ];

  it("lists each answer on one line and asks for an open assumption where the user does not know", () => {
    expect(missingAnswersMessage(fi.gate1Answer, entries)).toBe(
      [
        "Täydennän Gate 1:n puuttuvat tiedot:",
        "- Nykyprosessi: Laskut kirjataan käsin. Kenttä 'summa' tarkistetaan.",
        "- Odotettu arvo: en tiedä. Kirjaa kohtaan paras arviosi keskustelun perusteella ja lisää se avoimeksi oletukseksi, jotta Gate 1 voidaan hyväksyä.",
      ].join("\n"),
    );
  });

  it("is the text the chat reports back on: nothing to trim", () => {
    for (const labels of [fi.gate1Answer, en.gate1Answer]) {
      const message = missingAnswersMessage(labels, entries);
      expect(message).toBe(message.trim());
      expect(message.split("\n")).toHaveLength(3);
    }
  });

  it("asks the wizard for a value, since a placeholder keeps Gate 1 closed", () => {
    expect(en.gate1Answer.messageNotKnown).toMatch(/best estimate/);
    expect(en.gate1Answer.messageNotKnown).toMatch(/open assumption/);
    expect(fi.gate1Answer.messageNotKnown).toMatch(/paras arviosi/);
    expect(fi.gate1Answer.messageNotKnown).toMatch(/avoimeksi oletukseksi/);
  });
});
