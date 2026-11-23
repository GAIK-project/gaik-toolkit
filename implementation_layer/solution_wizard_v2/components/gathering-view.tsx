import type { Dict } from "@/lib/i18n";
import { PointMark } from "./point-mark";
import { RequirementAnswer } from "./requirement-answer";

// Gathering-phase center view (steps 1–2). No technical blueprint yet — that
// belongs to the design phase (step 5+). The session starts in the chat, open
// beside (or over) this view; here the requirements checklist fills up from
// the answers. The live agent keeps no checklist: there the chat is the page
// (lib/session-start) and this view is not shown.
export function GatheringView({
  points,
  answers,
  t,
}: {
  points: string[];
  answers: string[];
  t: Dict;
}) {
  const items = points;
  const total = items.length;
  const answered = answers.length;
  const pct = total ? Math.round((answered / total) * 100) : 0;
  const answerLabels = {
    ask: t.gatheringAsk,
    chip: t.gatheringAskChip,
    prefix: t.gatheringAskPrefix,
  };
  const markLabels = { answered: t.pointAnswered, open: t.pointOpen };

  return (
    <div className="mx-auto w-full max-w-2xl">
      <p className="max-w-prose text-sm leading-relaxed text-text-secondary">
        {t.gatheringPrompt}
      </p>

      <section className="mt-5 rounded-lg border border-border bg-surface">
        <div className="flex items-center justify-between gap-3 px-4 pb-2 pt-3">
          <h4 className="text-sm font-semibold text-text">{t.gate1ChecklistTitle}</h4>
          <span className="text-xs text-text-muted">
            {answered} / {total} {t.gate1Answered}
          </span>
        </div>
        <div
          className="mx-4 h-1 overflow-hidden rounded-full bg-surface-muted"
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={t.gate1ChecklistTitle}
        >
          <span className="block h-full rounded-full bg-brand" style={{ width: `${pct}%` }} />
        </div>
        <ul className="mt-2 divide-y divide-border">
          {items.map((q, i) => {
            const done = i < answered;
            return (
              <li key={i} className="flex items-start gap-2 px-4 py-1.5">
                <PointMark number={i + 1} done={done} labels={markLabels} className="sm:mt-1.5" />
                <span className="min-w-0 flex-1 sm:flex sm:items-start sm:justify-between sm:gap-4">
                  <span className="block min-w-0 sm:py-1.5">
                    <span className={`block text-sm ${done ? "text-text" : "text-text-secondary"}`}>
                      {q}
                    </span>
                    {done && answers[i] && (
                      <span className="mt-0.5 block break-words text-xs text-text-secondary">
                        {answers[i]}
                      </span>
                    )}
                  </span>
                  {/* Every open point has its button, in view without the
                      pointer; the point the wizard is on has the marked one. */}
                  {!done && (
                    <RequirementAnswer
                      number={i + 1}
                      question={q}
                      labels={answerLabels}
                      next={i === answered}
                    />
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
