"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import type { Blueprint, BlueprintStep, BlueprintStepType } from "@/lib/mock-sessions";
import type { Dict } from "@/lib/i18n";
import { planSettings } from "@/lib/plan-settings";
import { isSeedBlueprint, shownGoal } from "@/lib/blueprint-goal";
import { askInChat } from "@/lib/chat-events";
import { fillTemplate, quoteOneLine } from "@/lib/chat-template";
import {
  FIELD_TYPES,
  draftsFromFields,
  fieldChangeMessage,
  fieldChanges,
  fieldDraftProblem,
  type FieldDraft,
} from "@/lib/output-schema-edit";
import { Icon } from "@/components/icons";
import { FileIcon } from "@/components/file-icon";
import { StepNumber, StepTypeTag, stepTypeLabels } from "@/components/step-type";
import { usePageSend } from "@/components/use-page-send";
import type { FieldSpec } from "@/components/field-schema-editor";

// The Blueprint tab's read view (#23, the business-language plan): one card
// per step with its name, kind and description, and the component and its
// settings behind a disclosure. It was a tab of its own ("Suunnitelma") beside
// two others that showed the same steps; editing is one press away, at the end
// of the tab row. A step's
// type reads as it does in the form, the Workflow tab's list and the diagram's
// properties: the number on the type's colour, the type's icon and its name
// (components/step-type).

function stepReference(step: BlueprintStep, index: number, t: Dict) {
  const n = String(index + 1);
  return {
    key: `step:${step.id}`,
    // An unnamed step is "Vaihe 3", not "Vaihe 3 · ".
    label: fillTemplate(t.planStepRefLabel, { n, name: step.name.trim() }).replace(/\s*·\s*$/, ""),
    // The name and id are the agent's words: they travel as a marked quote.
    prefix: fillTemplate(t.planStepRefPrefix, {
      n,
      id: quoteOneLine(step.id, 80),
      name: quoteOneLine(step.name),
    }),
  };
}

function StepCard({
  step,
  index,
  typeLabel,
  t,
}: {
  step: BlueprintStep;
  index: number;
  typeLabel: Record<BlueprintStepType, string>;
  t: Dict;
}) {
  // A setting that holds JSON is for the form, not for an approver to read;
  // the card says how many it leaves out.
  const { readable: settings, hidden } = planSettings(step.settings);
  const component = step.component?.trim() ?? "";
  const hasDetails = component !== "" || settings.length > 0 || hidden > 0;
  const summary =
    component && settings.length > 0 ? t.planDetails : component ? t.planComponentLabel : t.planSettingsLabel;
  const reference = stepReference(step, index, t);
  return (
    <li
      className="rounded-lg border border-border bg-surface py-3 pl-3 pr-2 sm:pl-4"
      data-testid={`plan-step-${index}`}
    >
      <div className="flex items-start gap-3">
        <span className="mt-px flex">
          <StepNumber n={index + 1} type={step.type} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 pt-0.5">
            <h3 className="text-sm font-semibold text-text-strong">{step.name}</h3>
            <StepTypeTag type={step.type} label={typeLabel[step.type]} />
          </div>
          {step.description && (
            <p className="mt-1 text-sm leading-relaxed text-text-secondary">{step.description}</p>
          )}
          {hasDetails && (
            <details className="group mt-2">
              <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded text-xs font-medium text-text-muted transition-colors hover:text-text [&::-webkit-details-marker]:hidden">
                <Icon
                  name="chevronRight"
                  size={13}
                  className="transition-transform duration-150 ease-out group-open:rotate-90"
                />
                {summary}
              </summary>
              <dl className="mt-1.5 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 pl-[18px] text-xs">
                {component && (
                  <>
                    <dt className="text-text-muted">{t.planComponentLabel}</dt>
                    <dd className="break-words text-text">{component}</dd>
                  </>
                )}
                {settings.map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="font-mono text-text-muted">{k}</dt>
                    <dd className="break-words text-text">{v}</dd>
                  </div>
                ))}
              </dl>
              {hidden > 0 && (
                <p
                  className="mt-1.5 pl-[18px] text-xs text-text-muted"
                  data-testid={`plan-step-${index}-hidden-settings`}
                >
                  {hidden === 1
                    ? t.planHiddenSettingsOne
                    : t.planHiddenSettingsMany.replace("{n}", String(hidden))}
                </p>
              )}
            </details>
          )}
        </div>
        <button
          type="button"
          className="icon-btn -mt-1"
          onClick={() => askInChat(reference)}
          aria-label={`${t.planAskInChat}: ${reference.label}`}
          title={t.planAskInChat}
          data-testid={`plan-step-${index}-ask`}
        >
          <Icon name="messageSquareText" size={16} />
        </button>
      </div>
    </li>
  );
}

/**
 * The output fields the wizard agreed with the user (the blueprint's
 * target_output_spec, which the package's output schema is generated from):
 * each field's name, type and whether it is required. Closed until asked for.
 *
 * "Muokkaa kenttiä" at the heading turns the rows into a small form. The
 * agreed fields are the wizard's own record, which the page has no route to
 * write, so the form's result is one chat turn that names each change
 * (lib/output-schema-edit) and the wizard applies it; the page's new data
 * then brings the rows as they stand.
 */
function OutputSchema({ fields, t }: { fields: FieldSpec[]; t: Dict }) {
  const L = t.planSchema;
  const E = t.planSchemaEdit;
  const [open, setOpen] = useState(false);
  // The form's rows; null while the fields are only read.
  const [drafts, setDrafts] = useState<FieldDraft[] | null>(null);
  // The rows of a change on its way: offered again if it never reaches the wizard.
  const [pending, setPending] = useState<FieldDraft[] | null>(null);
  const { state, replying, send, reset } = usePageSend();
  const panelId = useId();
  const added = useRef(0);
  const editRef = useRef<HTMLButtonElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const moveFocus = useRef<"form" | "edit" | null>(null);

  const rows = drafts ?? (state === "failed" ? pending : null);
  const editing = rows !== null;
  const problem = rows ? fieldDraftProblem(rows) : null;
  const message = rows
    ? fieldChangeMessage(fieldChanges(fields, rows), { ...E.message, types: L.types })
    : "";

  // The focus follows the press that opened or closed the form.
  useEffect(() => {
    const to = moveFocus.current;
    moveFocus.current = null;
    if (to === "form") formRef.current?.querySelector<HTMLElement>("input")?.focus();
    if (to === "edit") editRef.current?.focus();
  }, [editing]);

  function setRow(key: string, change: Partial<FieldDraft>) {
    if (rows) setDrafts(rows.map((row) => (row.key === key ? { ...row, ...change } : row)));
  }

  function close() {
    moveFocus.current = "edit";
    setDrafts(null);
    setPending(null);
    reset();
  }

  return (
    <section className="@container rounded-lg border border-border bg-surface" data-testid="plan-schema">
      <div className="flex items-center gap-2 pr-2 sm:pr-3">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          // The form stays in view while it is being filled in.
          aria-disabled={editing || undefined}
          onClick={() => {
            if (!editing) setOpen((now) => !now);
          }}
          className={`flex min-w-0 flex-1 items-center gap-3 rounded-lg py-3 pl-3 pr-1 text-left transition-colors hover:bg-surface-muted/60 sm:pl-4 ${
            open ? "rounded-b-none" : ""
          }`}
          data-testid="plan-schema-toggle"
        >
          <span
            aria-hidden
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-surface-muted"
          >
            <FileIcon kind="json" size={16} />
          </span>
          <span className="text-sm font-semibold text-text-strong">{L.title}</span>
          <span className="text-xs text-text-muted">
            {fields.length === 1 ? L.countOne : L.countMany.replace("{n}", String(fields.length))}
          </span>
          <Icon
            name="chevronDown"
            size={16}
            className={`ml-auto text-text-muted transition-transform duration-150 ease-out motion-reduce:transition-none ${
              open ? "rotate-180" : ""
            }`}
          />
        </button>
        {!editing && state !== "sent" && (
          <button
            ref={editRef}
            type="button"
            className="inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1.5 text-xs font-medium text-text-muted transition-colors duration-150 hover:bg-surface-muted hover:text-text"
            aria-label={E.edit}
            title={E.edit}
            onClick={() => {
              moveFocus.current = "form";
              setOpen(true);
              setDrafts(draftsFromFields(fields));
            }}
            data-testid="plan-schema-edit"
          >
            <Icon name="pencil" size={13} />
            <span aria-hidden className="sr-only @lg:not-sr-only">
              {E.edit}
            </span>
          </button>
        )}
      </div>

      {open && (
        <div id={panelId} className="reveal-in border-t border-border">
          {state === "sent" && (
            <p
              role="status"
              className="flex items-center gap-2 border-b border-border px-3 py-2 text-xs text-text-muted sm:px-4"
            >
              <Icon name="loaderCircle" size={13} className="animate-spin motion-reduce:animate-none" />
              {t.changeHere.working}
            </p>
          )}
          {rows && state !== "sent" ? (
            <form
              ref={formRef}
              data-testid="plan-schema-form"
              onSubmit={(e) => {
                e.preventDefault();
                if (!message || problem || replying) return;
                setPending(rows);
                setDrafts(null);
                send(message);
              }}
              onKeyDown={(e) => {
                if (e.key === "Escape") close();
              }}
            >
              <ul className="divide-y divide-border">
                {rows.map((row, i) => {
                  const n = String(i + 1);
                  const named = row.name.trim() || E.unnamed;
                  return (
                    <li
                      key={row.key}
                      className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-x-3 gap-y-2 px-3 py-2.5 sm:px-4 @lg:grid-cols-[minmax(0,1fr)_9rem_auto_auto]"
                    >
                      <input
                        type="text"
                        value={row.name}
                        onChange={(e) => setRow(row.key, { name: e.target.value })}
                        aria-label={`${E.name} ${n}`}
                        placeholder={E.name}
                        maxLength={120}
                        autoComplete="off"
                        spellCheck={false}
                        className="input-field col-span-3 py-1.5 font-mono text-[13px] @lg:col-span-1"
                      />
                      <select
                        value={row.type}
                        onChange={(e) => setRow(row.key, { type: e.target.value as FieldSpec["type"] })}
                        aria-label={`${E.type}: ${named}`}
                        className="input-field py-1.5"
                      >
                        {FIELD_TYPES.map((type) => (
                          <option key={type} value={type}>
                            {L.types[type]}
                          </option>
                        ))}
                      </select>
                      <label className="inline-flex items-center gap-1.5 text-xs text-text-secondary">
                        <input
                          type="checkbox"
                          checked={row.required}
                          onChange={(e) => setRow(row.key, { required: e.target.checked })}
                          aria-label={`${L.required}: ${named}`}
                          className="h-3.5 w-3.5 accent-brand"
                        />
                        {L.required}
                      </label>
                      <button
                        type="button"
                        className="icon-btn"
                        aria-label={fillTemplate(E.remove, { name: named })}
                        title={fillTemplate(E.remove, { name: named })}
                        onClick={() => setDrafts(rows.filter((other) => other.key !== row.key))}
                      >
                        <Icon name="trash2" size={15} />
                      </button>
                      {row.type === "enum" && (
                        <input
                          type="text"
                          value={row.values}
                          onChange={(e) => setRow(row.key, { values: e.target.value })}
                          aria-label={`${E.values}: ${named}`}
                          placeholder={E.values}
                          maxLength={500}
                          autoComplete="off"
                          className="input-field col-span-3 py-1.5 @lg:col-span-4"
                        />
                      )}
                    </li>
                  );
                })}
              </ul>
              <div className="flex flex-wrap items-center gap-2 border-t border-border px-3 py-2.5 sm:px-4">
                <button
                  type="button"
                  className="inline-flex items-center gap-1 rounded-md px-2 py-1.5 text-xs font-medium text-brand-text transition-colors duration-150 hover:bg-brand-soft"
                  onClick={() => {
                    added.current += 1;
                    setDrafts([
                      ...rows,
                      { key: `added-${added.current}`, original: null, name: "", type: "text", required: false, values: "" },
                    ]);
                  }}
                  data-testid="plan-schema-add"
                >
                  <Icon name="plus" size={14} />
                  {E.add}
                </button>
                <p role="alert" className="min-w-0 flex-1 basis-40 text-xs text-danger-text">
                  {state === "failed" ? t.changeHere.failed : problem ? E.problems[problem] : ""}
                </p>
                <button type="button" onClick={close} className="btn-ghost px-3 py-1.5">
                  {t.changeHere.cancel}
                </button>
                <button
                  type="submit"
                  disabled={!message || problem !== null || replying}
                  className="btn-secondary px-3 py-1.5"
                >
                  <Icon name="send" size={14} />
                  {t.changeHere.send}
                </button>
              </div>
            </form>
          ) : (
            <ul className="divide-y divide-border" data-testid="plan-schema-fields">
              {fields.map((field) => (
                <li
                  key={field.name}
                  className="grid grid-cols-[minmax(0,1fr)_auto_5rem] items-baseline gap-x-4 gap-y-0.5 px-3 py-2 sm:px-4"
                >
                  <span className="break-words font-mono text-[13px] text-text">{field.name}</span>
                  <span className="text-xs text-text-secondary">{L.types[field.type]}</span>
                  <span className="text-right text-xs text-text-muted">{field.required ? L.required : ""}</span>
                  {field.rule && <p className="col-span-3 text-xs leading-relaxed text-text-muted">{field.rule}</p>}
                  {field.allowedValues && field.allowedValues.length > 0 && (
                    <p className="col-span-3 break-words text-xs leading-relaxed text-text-muted">
                      {L.allowed} {field.allowedValues.join(", ")}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

export function SolutionPlanView({
  blueprint,
  outputFields = [],
  t,
  note,
}: {
  blueprint: Blueprint;
  /** The agreed output fields; nothing is shown before there are any. */
  outputFields?: FieldSpec[];
  t: Dict;
  /** A line above the plan, e.g. what a change costs once the package is tested. */
  note?: ReactNode;
}) {
  const typeLabel = stepTypeLabels(t);
  // A new session's blueprint carries a placeholder where the goal will be.
  const goal = shownGoal(blueprint.goal);
  // That same blueprint's steps are the draft's, not the solution's: until the
  // wizard has written the real ones, the view says so in their place.
  const preparing = isSeedBlueprint(blueprint);

  return (
    <div className="flex max-w-4xl flex-col gap-4 pb-2 pr-1" data-testid="solution-plan-view">
      {note}
      {goal && (
        <p className="text-sm leading-relaxed text-text-secondary" data-testid="plan-goal">
          <span className="font-medium text-text-strong">{t.wsBlueprintGoal}:</span> {goal}
        </p>
      )}

      {outputFields.length > 0 && <OutputSchema fields={outputFields} t={t} />}

      {preparing ? (
        <p
          className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-text-muted"
          data-testid="plan-preparing"
        >
          {/* Under output fields that are already listed, only the steps are
              still to come: "the structure" read as if nothing were there. */}
          {outputFields.length > 0 ? t.planPreparingSteps : t.planPreparing}
        </p>
      ) : blueprint.steps.length === 0 ? (
        <p className="text-sm text-text-muted">{t.planEmptySteps}</p>
      ) : (
        <ol className="flex flex-col gap-2">
          {blueprint.steps.map((step, index) => (
            <StepCard key={step.id} step={step} index={index} typeLabel={typeLabel} t={t} />
          ))}
        </ol>
      )}
    </div>
  );
}
