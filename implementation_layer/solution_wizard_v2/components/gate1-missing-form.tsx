"use client";

import { useId, useState } from "react";
import { fillTemplate } from "@/lib/chat-template";
import { MISSING_ANSWER_MAX, missingAnswersMessage, type MissingAnswerLabels } from "@/lib/gate-guide";
import { usePageSend } from "./use-page-send";
import { Icon } from "./icons";

export type Gate1MissingLabels = MissingAnswerLabels & {
  /** What the fields are for, above them. */
  intro: string;
  /** The choice beside a field. */
  notKnown: string;
  /** Its accessible name, naming the item: {item}. */
  notKnownItem: string;
  send: string;
  /** In the fields' place while the wizard records the answers. */
  working: string;
  /** The answers never reached the wizard. */
  failed: string;
};

/**
 * Why Gate 1 cannot be approved yet, with the way out in the same place: one
 * field per item the wizard has not recorded, a "not known" choice for each,
 * and one button. The answers go to the wizard as one chat turn; an item
 * marked not known asks the wizard for its own estimate, recorded as an open
 * assumption, since an empty item keeps the approval closed. While the wizard
 * works on them the fields give way to a line saying so; the page's new data
 * then takes the answered items (or this whole notice) away.
 */
export function Gate1MissingForm({ items, labels }: { items: string[]; labels: Gate1MissingLabels }) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [unknown, setUnknown] = useState<Record<string, boolean>>({});
  const { state, replying, send } = usePageSend();
  const formId = useId();

  const entries = items
    .map((item) => ({ item, answer: (answers[item] ?? "").trim(), notKnown: Boolean(unknown[item]) }))
    .filter((entry) => entry.notKnown || entry.answer);

  return (
    <div
      data-testid="gate1-missing"
      className="mb-2.5 rounded-md border border-warning-border bg-warning-bg px-3 py-2.5 text-sm text-warning-text"
    >
      {state === "sent" ? (
        <p role="status" className="flex items-center gap-2">
          <Icon name="loaderCircle" size={16} className="animate-spin motion-reduce:animate-none" />
          {labels.working}
        </p>
      ) : (
        <form data-testid="gate1-missing-form" onSubmit={(e) => e.preventDefault()}>
          <p className="flex items-start gap-2">
            <Icon name="circleAlert" size={16} className="mt-0.5" />
            <span>{labels.intro}</span>
          </p>
          <div className="mt-2 grid gap-x-4 gap-y-2 @2xl:grid-cols-2">
            {items.map((item, i) => {
              const id = `${formId}-${i}`;
              const notKnown = Boolean(unknown[item]);
              return (
                <div key={item} className="min-w-0">
                  <div className="flex items-center justify-between gap-3">
                    <label htmlFor={id} className="font-medium text-text">
                      {item}
                    </label>
                    <label className="inline-flex shrink-0 items-center gap-1.5 text-xs text-text-secondary">
                      <input
                        type="checkbox"
                        checked={notKnown}
                        onChange={(e) => setUnknown((u) => ({ ...u, [item]: e.target.checked }))}
                        aria-label={fillTemplate(labels.notKnownItem, { item })}
                        className="h-3.5 w-3.5 accent-brand"
                      />
                      {labels.notKnown}
                    </label>
                  </div>
                  <textarea
                    id={id}
                    rows={1}
                    maxLength={MISSING_ANSWER_MAX}
                    value={answers[item] ?? ""}
                    disabled={notKnown}
                    onChange={(e) => setAnswers((a) => ({ ...a, [item]: e.target.value }))}
                    className="input-field mt-1 block max-h-28 min-h-[38px] resize-y field-sizing-content disabled:cursor-not-allowed disabled:opacity-50"
                  />
                </div>
              );
            })}
          </div>
          {state === "failed" && (
            <p role="alert" className="mt-2 text-xs text-danger-text">
              {labels.failed}
            </p>
          )}
          <div className="mt-2 flex justify-end">
            {/* Not a submit button: the bar's one submit is its approval, which
                "Show me" in the chat looks up by that. */}
            <button
              type="button"
              disabled={!entries.length || replying}
              onClick={() => send(missingAnswersMessage(labels, entries))}
              className="btn-secondary px-3 py-1.5"
            >
              <Icon name="send" size={14} />
              {labels.send}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
