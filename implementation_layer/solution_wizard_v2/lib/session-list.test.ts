import { describe, expect, it } from "vitest";
import {
  fillQuery,
  formatUpdated,
  formatUpdatedFull,
  gateMarks,
  groupSessionsByDay,
  matchesSearch,
  showsSearch,
  standing,
} from "./session-list";
import { buildGateStatus, GATE_STEPS } from "./wizard-state-machine";

// 9 Nov 2026, 10:00 in Finland (08:00 UTC).
const NOW = new Date("2026-11-09T08:00:00Z");
const at = (iso: string, title = iso) => ({ title, updatedAt: iso });

describe("groupSessionsByDay", () => {
  it("groups by the day in Finland and keeps the order", () => {
    const groups = groupSessionsByDay(
      [
        at("2026-11-09T07:00:00Z", "a"),
        // 00:30 in Finland on the 9th, though still the 8th in UTC.
        at("2026-11-08T22:30:00Z", "b"),
        at("2026-11-08T09:00:00Z", "c"),
        at("2026-11-04T09:00:00Z", "d"),
        at("2026-11-02T09:00:00Z", "e"),
      ],
      NOW,
    );
    expect(groups.map((g) => [g.day, g.sessions.map((s) => s.title)])).toEqual([
      ["today", ["a", "b"]],
      ["yesterday", ["c"]],
      ["week", ["d"]],
      ["earlier", ["e"]],
    ]);
  });

  it("leaves out empty groups", () => {
    expect(groupSessionsByDay([at("2026-10-01T09:00:00Z")], NOW).map((g) => g.day)).toEqual(["earlier"]);
  });

  const days = (sessions: { title: string; updatedAt: string }[], now: string) =>
    groupSessionsByDay(sessions, new Date(now)).map((g) => [g.day, g.sessions.map((s) => s.title)]);

  it("counts calendar days over the change to summer time, a day of 23 hours", () => {
    // Clocks went forward on Sunday 28 Mar 2027. Monday 00:30 in Finland is
    // 21:30 UTC on Sunday; 24 hours earlier it was still Saturday there.
    expect(
      days(
        [
          at("2027-03-28T09:00:00Z", "sunday"),
          at("2027-03-27T09:00:00Z", "saturday"),
          at("2027-03-23T09:00:00Z", "tuesday"),
          at("2027-03-22T09:00:00Z", "monday before"),
        ],
        "2027-03-28T21:30:00Z",
      ),
    ).toEqual([
      ["yesterday", ["sunday"]],
      ["week", ["saturday", "tuesday"]],
      ["earlier", ["monday before"]],
    ]);
  });

  it("counts calendar days over the change to winter time, a day of 25 hours", () => {
    // Clocks went back on Sunday 25 Oct 2026. Sunday 23:30 in Finland is
    // 21:30 UTC; 24 hours earlier it was already Sunday there, 00:30.
    expect(
      days(
        [
          at("2026-10-25T09:00:00Z", "sunday"),
          at("2026-10-24T09:00:00Z", "saturday"),
          at("2026-10-19T09:00:00Z", "monday"),
          at("2026-10-18T09:00:00Z", "sunday before"),
        ],
        "2026-10-25T21:30:00Z",
      ),
    ).toEqual([
      ["today", ["sunday"]],
      ["yesterday", ["saturday"]],
      ["week", ["monday"]],
      ["earlier", ["sunday before"]],
    ]);
  });
});

describe("matchesSearch", () => {
  it("ignores case, Finnish letters included", () => {
    expect(matchesSearch("Ostotilaukset ÄÖ", "äö")).toBe(true);
    expect(matchesSearch("R32 UC04", "uc04")).toBe(true);
    expect(matchesSearch("R32 UC04", "uc05")).toBe(false);
  });
});

describe("showsSearch", () => {
  it("shows the field from six sessions on", () => {
    expect(showsSearch(5, "")).toBe(false);
    expect(showsSearch(6, "")).toBe(true);
  });

  it("keeps the field while a search is on, so a filtered list can be cleared", () => {
    expect(showsSearch(5, "uc04")).toBe(true);
    expect(showsSearch(1, "uc04")).toBe(true);
  });

  it("has nothing to search without sessions", () => {
    expect(showsSearch(0, "uc04")).toBe(false);
  });
});

describe("fillQuery", () => {
  it("puts the search in as typed, replacement patterns included", () => {
    expect(fillQuery('No sessions match "{q}".', "$& $1 $$")).toBe('No sessions match "$& $1 $$".');
  });
});

describe("gateMarks", () => {
  const marks = (step: number, gateStatus = buildGateStatus(step)) =>
    gateMarks(step, GATE_STEPS, gateStatus);

  it("marks the stage a session works on, the gates behind it and the ones ahead", () => {
    expect(marks(1)).toEqual(["open", "ahead", "ahead", "ahead"]);
    expect(marks(6)).toEqual(["approved", "open", "ahead", "ahead"]);
    expect(marks(10)).toEqual(["approved", "approved", "open", "ahead"]);
    expect(marks(12)).toEqual(["approved", "approved", "approved", "open"]);
  });

  it("says when the session stands on a gate, where the next move is the user's", () => {
    expect(marks(4)).toEqual(["waiting", "ahead", "ahead", "ahead"]);
    expect(marks(9)).toEqual(["approved", "waiting", "ahead", "ahead"]);
    expect(marks(9, { ...buildGateStatus(9), 9: "rejected" })).toEqual([
      "approved",
      "rejected",
      "ahead",
      "ahead",
    ]);
  });

  it("keeps the last gate open until it is approved, though the step never moves past it", () => {
    expect(marks(13)).toEqual(["approved", "approved", "approved", "waiting"]);
    expect(marks(13, { ...buildGateStatus(13), 13: "approved" })).toEqual([
      "approved",
      "approved",
      "approved",
      "approved",
    ]);
  });
});

describe("standing", () => {
  it("is done only when every gate is approved", () => {
    expect(standing(["approved", "approved", "approved", "approved"])).toBe("done");
    expect(standing(["approved", "approved", "approved", "waiting"])).toBe("waiting");
  });

  it("follows the gate the session stands on", () => {
    expect(standing(["approved", "open", "ahead", "ahead"])).toBe("open");
    expect(standing(["approved", "waiting", "ahead", "ahead"])).toBe("waiting");
    expect(standing(["approved", "rejected", "ahead", "ahead"])).toBe("rejected");
  });
});

describe("formatUpdated", () => {
  // 00:30 on 9 Nov in Finland, still 8 Nov in UTC.
  const NIGHT = "2026-11-08T22:30:00Z";

  it("gives the time under today and yesterday, in Finland's time", () => {
    expect(formatUpdated(NIGHT, "today", "fi-FI")).toBe("0.30");
    expect(formatUpdated("2026-11-08T13:05:00Z", "yesterday", "fi-FI")).toBe("15.05");
  });

  it("gives the weekday and date within the week, and the full date before it", () => {
    expect(formatUpdated(NIGHT, "week", "fi-FI")).toBe("ma 9.11.");
    expect(formatUpdated(NIGHT, "earlier", "fi-FI")).toBe("9.11.2026");
    expect(formatUpdated(NIGHT, "week", "en-GB")).toBe("Mon 9 Nov");
  });

  it("gives the date and the time for the hover hint", () => {
    expect(formatUpdatedFull(NIGHT, "fi-FI")).toMatch(/^9\.11\.2026 .*0\.30$/);
  });
});
