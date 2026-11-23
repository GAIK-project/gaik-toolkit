import type { Dict } from "@/lib/i18n";
import type { Assumption, BusinessContext } from "@/lib/sessions";
import { fillTemplate, quoteOneLine } from "@/lib/chat-template";
import { ChangeInPlace } from "@/components/ask-in-chat-button";
import { Icon } from "@/components/icons";
import { PointMark } from "@/components/point-mark";
import type { ChangeChoices } from "@/lib/change-choice";
import { KNOWLEDGE_PROCESSES, known, knownList, knowledgeProcess, type KnowledgeProcess } from "@/lib/known-values";
import { plainLabel, plainLabelCapitalized } from "@/lib/plain-label";

/**
 * What Gate 1 still lacks before it can be approved: the wizard has to have
 * captured at least the current process and the expected value. The names go
 * into the decision bar's hint, so the SME knows what to keep answering.
 */
export function gate1Missing(businessContext: BusinessContext | null | undefined, t: Dict): string[] {
  const missing: string[] = [];
  if (!known(businessContext?.currentProcess)) missing.push(t.bcCurrentProcess);
  if (!knownList(businessContext?.expectedValue).length) missing.push(t.bcExpectedValue);
  return missing;
}

// Focus view for Gate 1: the requirements gathered in steps 1–3, the business
// framing the agent captured into the draft blueprint (current process /
// expected value / knowledge processes) and the assumptions it recorded, so the
// SME reviews the business intent, not just JSON. It reads as one document:
// plain headings on one sheet, no cards inside it, and the agent's identifiers
// ("knowledge_capture") in plain words. Each item can be corrected where it
// stands: a field opens under it, and the correction goes to the wizard as a
// chat turn. Where the value is one of a known few (the knowledge processes,
// whether an assumption holds) the correction is a choice, with the field left
// for the rest. The decision itself is the page's gate decision bar.
export function Gate1Review({
  points,
  answers,
  businessContext,
  assumptions = [],
  t,
}: {
  points: string[];
  answers: string[];
  businessContext?: BusinessContext | null;
  assumptions?: Assumption[];
  t: Dict;
}) {
  const items = points;
  const answered = answers.length;
  const bc = businessContext ?? null;
  const ctx = bc && {
    domain: known(bc.domain),
    currentProcess: known(bc.currentProcess),
    expectedValue: knownList(bc.expectedValue),
    knowledgeProcesses: knowledgeRows(knownList(bc.knowledgeProcesses), t),
    painPoints: knownList(bc.painPoints),
    intendedUsers: knownList(bc.intendedUsers),
    reviewers: knownList(bc.reviewers),
  };
  const change = {
    change: t.changeHere.change,
    field: t.changeHere.field,
    send: t.changeHere.send,
    cancel: t.changeHere.cancel,
    working: t.changeHere.working,
    failed: t.changeHere.failed,
  };
  // One item of the business context: its name, what the wizard recorded, and
  // the control that corrects it in place. The item's text is the agent's, so
  // it travels as a quote on one line.
  const field = (
    key: string,
    label: string,
    value: string | string[],
    asList = false,
    choices?: ChangeChoices,
  ) => {
    const values = Array.isArray(value) ? value : [value];
    return (
      <ChangeInPlace
        key={key}
        term={label}
        name={fillTemplate(t.changeHere.item, { item: label })}
        prefix={fillTemplate(t.bcPrefix, { field: label, text: quoteOneLine(values.join("; ")) })}
        labels={change}
        choices={choices}
      >
        {key === "knowledgeProcesses" && ctx ? (
          // Each process with one plain line on what it means.
          <ul className="space-y-1.5">
            {ctx.knowledgeProcesses.map((row) => (
              <li key={row.label}>
                <span>{row.label}</span>
                {row.help && <span className="block text-[13px] text-text-muted">{row.help}</span>}
              </li>
            ))}
          </ul>
        ) : asList && values.length > 1 ? (
          <ul className="list-disc space-y-0.5 pl-5">
            {values.map((v, i) => (
              <li key={i}>{v}</li>
            ))}
          </ul>
        ) : (
          values.join(", ")
        )}
      </ChangeInPlace>
    );
  };
  // An item the wizard has not recorded is a row of the same list: its name,
  // that it is not known yet, and "Lisää", which opens the same field in place.
  const missing = (key: string, label: string) => (
    <ChangeInPlace
      key={key}
      term={label}
      name={fillTemplate(t.bcAddItem, { item: label })}
      prefix={fillTemplate(t.bcAddPrefix, { field: label })}
      labels={{ ...change, change: t.bcAdd, field: t.bcAddField }}
      add
    >
      <span className="text-text-muted" data-testid="bc-not-known">
        {t.bcNotKnown}
      </span>
    </ChangeInPlace>
  );
  // The wizard's own three knowledge processes: a correction picks among them.
  const knowledgeChoices: ChangeChoices = {
    legend: t.changeChoice.knowledgeLegend,
    multiple: true,
    options: KNOWLEDGE_PROCESSES.map((process) => ({
      value: process,
      label: plainLabelCapitalized(process, t.bcKnowledgeProcessLabels),
      description: t.bcKnowledgeProcessHelp[process],
      sent: t.changeChoice.knowledgeSent[process],
    })),
    selected: ctx ? ctx.knowledgeProcesses.flatMap((row) => (row.process ? [row.process] : [])) : [],
    message: t.changeChoice.knowledgeMessage,
    other: t.changeChoice.knowledgeOther,
  };
  // An assumption holds or it does not; what is right instead is written under the choice.
  const holdsChoices = (confirmed: boolean): ChangeChoices => ({
    legend: t.changeChoice.assumptionLegend,
    options: [
      { value: "yes", label: t.changeChoice.holds, sent: t.changeChoice.holdsMessage },
      { value: "no", label: t.changeChoice.holdsNot, sent: t.changeChoice.holdsNotMessage },
    ],
    selected: confirmed ? ["yes"] : [],
    message: "{choice}",
    other: t.changeHere.field,
  });
  const heading = "text-base font-semibold text-text";
  const section = "px-5 py-5 sm:px-7";
  const empty = items.length === 0 && !ctx && assumptions.length === 0;

  if (empty) {
    return (
      <p
        className="mx-auto w-full max-w-3xl py-10 text-center text-sm text-text-muted"
        data-testid="gate1-review-empty"
      >
        {t.gate1ReviewEmpty}
      </p>
    );
  }

  return (
    <article
      className="mx-auto my-2 w-full max-w-3xl divide-y divide-border rounded-xl border border-border bg-surface"
      data-testid="gate1-review"
    >
      {/* The live agent keeps no requirement list (it is the mock store's):
          without points the gathered model below is the review. */}
      {items.length > 0 && (
        <section className={section}>
          <h2 className={heading}>{t.gate1ChecklistTitle}</h2>
          <p className="mt-0.5 text-sm text-text-muted">
            {answered} / {items.length} {t.gate1Answered}
          </p>
          <ul className="mt-3 space-y-2.5">
            {items.map((q, i) => {
              const done = i < answered;
              return (
                <li key={i} className="flex items-start gap-2 text-sm">
                  <PointMark
                    number={i + 1}
                    done={done}
                    labels={{ answered: t.pointAnswered, open: t.pointOpen }}
                  />
                  <span className="min-w-0 [overflow-wrap:anywhere]">
                    <span className={`block ${done ? "text-text" : "text-text-secondary"}`}>{q}</span>
                    {done && answers[i] && (
                      <span className="mt-0.5 block text-text-secondary">{answers[i]}</span>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {ctx && (
        <section className={section}>
          <h2 className={heading}>{t.bcTitle}</h2>
          {ctx.domain && (
            <p className="mt-0.5 text-sm text-text-muted [overflow-wrap:anywhere]">
              {t.bcDomain}: {plainLabelCapitalized(ctx.domain)}
            </p>
          )}
          <dl className="mt-4 space-y-4">
            {ctx.currentProcess
              ? field("currentProcess", t.bcCurrentProcess, ctx.currentProcess)
              : missing("currentProcess", t.bcCurrentProcess)}
            {ctx.expectedValue.length > 0
              ? field("expectedValue", t.bcExpectedValue, ctx.expectedValue, true)
              : missing("expectedValue", t.bcExpectedValue)}
            {ctx.knowledgeProcesses.length > 0 &&
              field(
                "knowledgeProcesses",
                t.bcKnowledgeProcesses,
                ctx.knowledgeProcesses.map((row) => row.label),
                false,
                knowledgeChoices,
              )}
            {ctx.painPoints.length > 0
              ? field("painPoints", t.bcPainPoints, ctx.painPoints, true)
              : missing("painPoints", t.bcPainPoints)}
            {ctx.intendedUsers.length > 0
              ? field("intendedUsers", t.bcUsers, ctx.intendedUsers)
              : missing("intendedUsers", t.bcUsers)}
            {ctx.reviewers.length > 0 && field("reviewers", t.bcReviewers, ctx.reviewers)}
          </dl>
        </section>
      )}

      {assumptions.length > 0 && (
        <section className={section}>
          <h2 className={heading}>{t.asmTitle}</h2>
          <p className="mt-0.5 text-sm text-text-muted">{t.asmIntro}</p>
          <ol className="mt-3 divide-y divide-border" data-testid="gate1-assumptions">
            {assumptions.map((a, i) => {
              const done = a.status === "confirmed";
              const n = String(i + 1);
              const chip = fillTemplate(t.asmChip, { n });
              // The agent's loose words ("data structure", "component_selection"):
              // the page's own word where it has one, as written otherwise.
              const impact = (a.impact ?? "").trim() ? plainLabel(a.impact, t.asmImpactLabels) : "";
              return (
                <li key={a.id || i} className="py-3 text-sm last:pb-0">
                  <ChangeInPlace
                    name={fillTemplate(t.changeHere.item, { item: chip })}
                    prefix={fillTemplate(t.asmPrefix, { n, text: quoteOneLine(a.text) })}
                    labels={change}
                    choices={holdsChoices(done)}
                    // Under the assumption's text, past its number.
                    formClassName="pl-7"
                  >
                    {/* The row's number is drawn, not written: the list is an
                        ordered one, so text copied from it (or read aloud)
                        already carries each item's number, once. */}
                    <span
                      className="w-4 shrink-0 text-right tabular-nums text-text-muted before:content-[attr(data-n)]"
                      data-n={`${n}.`}
                      aria-hidden
                    />
                    <div className="min-w-0 flex-1 [overflow-wrap:anywhere]">
                      <p className="text-text">{a.text}</p>
                      {/* A second, quiet line: the row's one status, then what it affects. */}
                      <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-text-muted">
                        <span
                          className={`inline-flex items-center gap-1 font-medium ${
                            done ? "text-text-muted" : "text-warning-text"
                          }`}
                          data-testid="assumption-status"
                        >
                          <Icon name={done ? "check" : "circleDot"} size={13} />
                          {done ? t.asmConfirmed : t.asmUnconfirmed}
                        </span>
                        {impact && (
                          <>
                            <span aria-hidden>·</span>
                            <span data-testid="assumption-impact">{fillTemplate(t.asmImpact, { impact })}</span>
                          </>
                        )}
                      </p>
                    </div>
                  </ChangeInPlace>
                </li>
              );
            })}
          </ol>
        </section>
      )}
    </article>
  );
}

type KnowledgeRow = { label: string; process: KnowledgeProcess | null; help?: string };

/**
 * The knowledge processes as the sheet lists them: each in plain words, a
 * known one with a line on what it means, and two values that read the same
 * shown once.
 */
function knowledgeRows(values: string[], t: Dict): KnowledgeRow[] {
  const rows = new Map<string, KnowledgeRow>();
  for (const value of values) {
    const process = knowledgeProcess(value);
    const label = plainLabelCapitalized(process ?? value, t.bcKnowledgeProcessLabels);
    if (!rows.has(label)) {
      rows.set(label, { label, process, ...(process ? { help: t.bcKnowledgeProcessHelp[process] } : {}) });
    }
  }
  return [...rows.values()];
}
