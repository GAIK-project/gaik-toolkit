import { stageState } from "@/lib/gate-timeline-state";
import type { GateStatus } from "@/lib/wizard-state-machine";

/** The day groups of the session list, newest first. */
export type SessionDay = "today" | "yesterday" | "week" | "earlier";

// Days are counted in Finland's time, where the wizard's users are: the server
// runs on UTC, and a session from 01:30 would otherwise fall on "yesterday".
const TIME_ZONE = "Europe/Helsinki";

/** "2026-11-09": the calendar day of `date` in Finland, comparable as text. */
function dayKey(date: Date): string {
  return date.toLocaleDateString("sv-SE", { timeZone: TIME_ZONE });
}

/**
 * The calendar day `days` before `key`. Counted on the calendar and not as
 * 24-hour steps back from now: the day the clocks change has 23 or 25 hours.
 */
function daysBefore(key: string, days: number): string {
  const [year, month, day] = key.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day - days)).toISOString().slice(0, 10);
}

/**
 * Sessions grouped by the day they were last updated: today, yesterday, the
 * five days before, and earlier. Order within a group is kept, and empty
 * groups are left out.
 */
export function groupSessionsByDay<T extends { updatedAt: string }>(
  sessions: T[],
  now: Date,
): { day: SessionDay; sessions: T[] }[] {
  const today = dayKey(now);
  const yesterday = daysBefore(today, 1);
  const weekStart = daysBefore(today, 6);
  const groups: Record<SessionDay, T[]> = { today: [], yesterday: [], week: [], earlier: [] };
  for (const session of sessions) {
    const key = dayKey(new Date(session.updatedAt));
    if (key >= today) groups.today.push(session);
    else if (key === yesterday) groups.yesterday.push(session);
    else if (key >= weekStart) groups.week.push(session);
    else groups.earlier.push(session);
  }
  return (["today", "yesterday", "week", "earlier"] as const)
    .filter((day) => groups[day].length > 0)
    .map((day) => ({ day, sessions: groups[day] }));
}

/** Whether a session's title holds the search, ignoring case. */
export function matchesSearch(title: string, query: string): boolean {
  return title.toLocaleLowerCase("fi").includes(query.toLocaleLowerCase("fi"));
}

// The search field shows from this many sessions on.
const SEARCH_FROM = 6;

/**
 * Whether the list shows its search field. A search that is on keeps the field
 * below the limit too, so a filtered list always shows what it is filtered by
 * and can be cleared. The list is filtered only when this holds.
 */
export function showsSearch(sessionCount: number, query: string): boolean {
  return sessionCount >= SEARCH_FROM || (sessionCount > 0 && query !== "");
}

/** `template` with "{q}" filled in as typed: "$&" in a search stays "$&". */
export function fillQuery(template: string, query: string): string {
  return template.replace("{q}", () => query);
}

/** One gate's stage on a session row: passed, being worked on, or still ahead. */
export type GateMark = "approved" | "open" | "waiting" | "rejected" | "ahead";

/**
 * Where a session stands at each gate, Gate 1 first, by the same rule as the
 * session page's timeline. "waiting" and "rejected" are a session that stands
 * on the gate itself: the next move there is the user's.
 */
export function gateMarks(
  step: number,
  gateSteps: readonly number[],
  gateStatus: Record<number, GateStatus>,
): GateMark[] {
  return gateSteps.map((gate, i) => {
    const first = i === 0 ? 1 : gateSteps[i - 1] + 1;
    const state = stageState(step, { first, last: gate }, gate, gateStatus);
    if (state === "approved") return "approved";
    if (state === "pending") return "ahead";
    if (step !== gate) return "open";
    return gateStatus[gate] === "rejected" ? "rejected" : "waiting";
  });
}

/** What a row says about the whole session. Done means every gate is approved. */
export type Standing = "done" | "waiting" | "rejected" | "open";

export function standing(marks: GateMark[]): Standing {
  if (marks.every((mark) => mark === "approved")) return "done";
  if (marks.includes("rejected")) return "rejected";
  return marks.includes("waiting") ? "waiting" : "open";
}

/**
 * When a session was last touched, as short as its day group allows: the time
 * under "today" and "yesterday", the weekday and date within the week, the
 * full date before that. In Finland's time, like the groups.
 */
export function formatUpdated(iso: string, day: SessionDay, dateLocale: string): string {
  const date = new Date(iso);
  if (day === "today" || day === "yesterday") {
    return date.toLocaleTimeString(dateLocale, {
      hour: "numeric",
      minute: "2-digit",
      timeZone: TIME_ZONE,
    });
  }
  return date.toLocaleDateString(
    dateLocale,
    day === "week"
      ? { weekday: "short", day: "numeric", month: "short", timeZone: TIME_ZONE }
      : { day: "numeric", month: "numeric", year: "numeric", timeZone: TIME_ZONE },
  );
}

/** The full date and time of the last update, for the hover hint. */
export function formatUpdatedFull(iso: string, dateLocale: string): string {
  return new Date(iso).toLocaleString(dateLocale, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: TIME_ZONE,
  });
}
