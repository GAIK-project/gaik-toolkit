import type { SessionRow } from "@/components/sidebar-sessions";
import { DATE_LOCALE, type Dict, type Locale } from "@/lib/i18n";
import {
  formatUpdated,
  formatUpdatedFull,
  gateMarks,
  groupSessionsByDay,
  standing,
} from "@/lib/session-list";
import { GATE_STEPS, PHASE_COUNT, type WizardSession } from "@/lib/sessions";

/**
 * The user's sessions as the sidebar lists them, newest day first. Every text
 * of a row is made here, on the server, in the user's language and in
 * Finland's time, so the browser formats no dates and shows what was rendered.
 */
export function sessionRows(
  sessions: Pick<WizardSession, "id" | "title" | "step" | "gateStatus" | "updatedAt">[],
  now: Date,
  locale: Locale,
  t: Dict,
): SessionRow[] {
  return groupSessionsByDay(sessions, now).flatMap(({ day, sessions: daySessions }) =>
    daySessions.map((s) => {
      const marks = gateMarks(s.step, GATE_STEPS, s.gateStatus);
      const where = standing(marks);
      return {
        id: s.id,
        title: s.title,
        day,
        marks,
        standing: where,
        stepLabel: `${t.step} ${s.step}/${PHASE_COUNT}`,
        phase: where === "done" ? "" : (t.phases[s.step - 1] ?? ""),
        updatedIso: s.updatedAt,
        updated: formatUpdated(s.updatedAt, day, DATE_LOCALE[locale]),
        updatedFull: `${t.updated} ${formatUpdatedFull(s.updatedAt, DATE_LOCALE[locale])}`,
      };
    }),
  );
}
