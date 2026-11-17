"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { referenceMessage } from "@/lib/chat-reference";
import { choiceCorrection, type ChangeChoices } from "@/lib/change-choice";
import { usePageSend } from "./use-page-send";
import { Icon } from "./icons";

/** Longest correction the field takes; the chat allows far more. */
const CORRECTION_MAX = 2000;

export type ChangeInPlaceLabels = {
  /** The control beside the item ("Muuta"). */
  change: string;
  /** The field's label ("Mikä on oikein?"). */
  field: string;
  send: string;
  cancel: string;
  /** In the control's place while the wizard works on the correction. */
  working: string;
  /** The correction never reached the wizard. */
  failed: string;
};

/**
 * One item on the page (an assumption, a business-context item) with a small
 * button that is always in view, also on a touch screen. It opens a field
 * under the item; what the user writes there goes to the wizard as a chat turn
 * that starts with `prefix`, the line naming the item, exactly as a reference
 * typed under in the chat would. The item is corrected where it is read.
 *
 * `term` lays the item out as a definition (its name, the control, then the
 * value); without it the control sits at the end of the row.
 *
 * An item whose value is one of a known few takes `choices`: the options
 * stand above the field, and what was chosen goes to the wizard in the same
 * message, with the field left for anything the options do not cover.
 */
export function ChangeInPlace({
  prefix,
  name,
  labels,
  term,
  choices,
  add = false,
  formClassName = "",
  children,
}: {
  /** The line the message starts with (see ChatReference.prefix). */
  prefix: string;
  /** The control's accessible name, naming the item ("Muuta: Oletus 2"). */
  name: string;
  labels: ChangeInPlaceLabels;
  /** The item's name, when it is laid out as a term and its value. */
  term?: ReactNode;
  /** The item's known values, offered in place of free text alone. */
  choices?: ChangeChoices;
  /** The item has no value yet: the control adds one (a plus, not a pencil). */
  add?: boolean;
  /** Lines the field up with the item's text where the row starts with something else. */
  formClassName?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const { state, replying, send, reset } = usePageSend();
  const fieldId = useId();
  const formRef = useRef<HTMLFormElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  // A correction that never reached the wizard is offered again, as written.
  const editing = open || state === "failed";
  // What the correction says under the item's line.
  const correction = choices ? choiceCorrection(choices, picked, text) : text;

  // The form's first control: the first option, or the field where there are none.
  useEffect(() => {
    if (open) formRef.current?.querySelector<HTMLElement>("input, textarea")?.focus();
  }, [open]);

  // Cancelling drops what was written and chosen, also after a send that failed.
  function close() {
    setOpen(false);
    setText("");
    setPicked([]);
    reset();
    triggerRef.current?.focus();
  }

  function pick(value: string, on: boolean) {
    if (!choices?.multiple) return setPicked(on ? [value] : []);
    setPicked((now) => (on ? [...now.filter((v) => v !== value), value] : now.filter((v) => v !== value)));
  }

  const control =
    state === "sent" ? (
      <span role="status" className="inline-flex shrink-0 items-center gap-1 text-xs text-text-muted">
        <Icon name="loaderCircle" size={13} className="animate-spin motion-reduce:animate-none" />
        {labels.working}
      </span>
    ) : (
      <button
        ref={triggerRef}
        type="button"
        aria-label={name}
        aria-expanded={editing}
        onClick={() => {
          if (editing) return close();
          // What the last correction said has gone to the wizard.
          setText("");
          setPicked(choices?.selected ?? []);
          setOpen(true);
        }}
        // A button with an edge: grey text alone did not say it can be pressed.
        className="btn-inline"
      >
        <Icon name={add ? "plus" : "pencil"} size={13} />
        {labels.change}
      </button>
    );

  const form = editing && state !== "sent" && (
    <form
      ref={formRef}
      onSubmit={(e) => {
        e.preventDefault();
        const message = referenceMessage(prefix, correction);
        if (!message || replying) return;
        setOpen(false);
        send(message);
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") close();
      }}
      className={`mt-2 space-y-2 ${formClassName} transition-[opacity,translate] duration-150 ease-out starting:translate-y-1 starting:opacity-0 motion-reduce:transition-none`}
    >
      {choices && (
        <fieldset className="space-y-1.5">
          <legend className="mb-1.5 text-xs font-medium text-text-secondary">{choices.legend}</legend>
          {choices.options.map((option) => (
            <label key={option.value} className="flex items-start gap-2 text-sm text-text">
              <input
                type={choices.multiple ? "checkbox" : "radio"}
                name={`${fieldId}-choice`}
                value={option.value}
                checked={picked.includes(option.value)}
                onChange={(e) => pick(option.value, e.target.checked)}
                className="mt-1 h-3.5 w-3.5 shrink-0 accent-brand"
              />
              <span className="min-w-0">
                {option.label}
                {option.description && (
                  <span className="block text-xs text-text-muted">{option.description}</span>
                )}
              </span>
            </label>
          ))}
        </fieldset>
      )}
      <label htmlFor={fieldId} className="block text-xs font-medium text-text-secondary">
        {choices ? choices.other : labels.field}
      </label>
      <textarea
        id={fieldId}
        rows={2}
        maxLength={CORRECTION_MAX}
        value={text}
        onChange={(e) => setText(e.target.value)}
        className="input-field resize-y"
      />
      {state === "failed" && (
        <p role="alert" className="text-xs text-danger-text">
          {labels.failed}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <button type="button" onClick={close} className="btn-ghost px-3 py-1.5">
          {labels.cancel}
        </button>
        <button type="submit" disabled={!correction.trim() || replying} className="btn-secondary px-3 py-1.5">
          <Icon name="send" size={14} />
          {labels.send}
        </button>
      </div>
    </form>
  );

  if (term !== undefined) {
    return (
      <div>
        <dt className="flex items-center justify-between gap-3 text-sm font-medium leading-4 text-text-muted">
          {term}
          {control}
        </dt>
        <dd className="mt-0.5 text-sm text-text [overflow-wrap:anywhere]">{children}</dd>
        {form && <dd>{form}</dd>}
      </div>
    );
  }
  return (
    <>
      <div className="flex items-start gap-3">
        {children}
        {control}
      </div>
      {form}
    </>
  );
}
