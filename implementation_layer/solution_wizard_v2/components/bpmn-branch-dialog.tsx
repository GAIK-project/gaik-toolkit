"use client";

import { useEffect, useId, useRef, useState } from "react";
import {
  DECISION_END,
  MAX_BRANCHES,
  MAX_CONDITION_CHARS,
  MAX_NAME_CHARS,
  MIN_BRANCHES,
  REWORK_END,
  REWORK_LOOP_TO,
  type DecisionBranch,
} from "@/lib/blueprint-ops";
import { decisionProblem, reworkProblem, type DecisionValues, type ReworkValues } from "@/lib/bpmn-canvas-ops";
import { fillTemplate } from "@/lib/chat-template";
import { Icon } from "@/components/icons";
import type { Dict } from "@/lib/i18n";

type Row = DecisionBranch & { key: number };

/** Keys for the branch rows, so a removed row takes its typed text with it. */
let rowKeys = 0;
const row = (b: DecisionBranch): Row => ({ ...b, key: ++rowKeys });

/**
 * A business decision's name and branches: each branch a condition and the
 * step it leads to (or the end). Opened by a step's "Add decision after" and
 * by a decision gateway's Edit, prefilled then. It opens as it mounts and
 * says what keeps the values from being a decision; Save hands them to
 * `onSave`, which sends the operation through the canvas's one gate. A
 * refusal keeps the dialog open with what was typed, and `error` says why.
 */
export function BpmnBranchDialog({
  mode,
  initial,
  steps,
  busy,
  error,
  onSave,
  onClose,
  t,
}: {
  mode: "add" | "edit";
  initial: DecisionValues;
  /** The steps a branch can lead to, in order; the end comes after them. */
  steps: { id: string; name: string }[];
  /** An edit is on its way: nothing can be saved. */
  busy: boolean;
  /** Why the last save was refused, in the UI language. */
  error: string | null;
  /** True once the decision is saved: the dialog closes then. */
  onSave: (values: DecisionValues) => Promise<boolean>;
  onClose: () => void;
  t: Dict;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [name, setName] = useState(initial.name);
  const [rows, setRows] = useState<Row[]>(() => {
    const given = initial.branches.map(row);
    while (given.length < MIN_BRANCHES) given.push(row({ condition: "", target: "" }));
    return given;
  });

  useEffect(() => {
    const el = dialog.current;
    if (el && !el.open) el.showModal();
  }, []);

  const values: DecisionValues = { name, branches: rows.map(({ condition, target }) => ({ condition, target })) };
  const problem = decisionProblem(values);
  // A target the steps no longer have (an agent's decision to a step removed since) stays pickable as it is.
  const known = new Set([...steps.map((s) => s.id), DECISION_END]);

  function update(key: number, change: Partial<DecisionBranch>) {
    setRows((current) => current.map((r) => (r.key === key ? { ...r, ...change } : r)));
  }

  async function save() {
    if (problem || busy) return;
    if (await onSave(values)) dialog.current?.close();
  }

  return (
    <dialog
      ref={dialog}
      onClose={onClose}
      aria-labelledby={titleId}
      data-testid="bpmn-branch-dialog"
      className="m-auto max-h-[calc(100dvh-2rem)] w-[min(34rem,calc(100vw-2rem))] overflow-y-auto rounded-lg border border-border bg-surface p-5 text-text shadow-lg backdrop:bg-black/40"
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <h2 id={titleId} className="text-base font-semibold text-text-strong">
          {mode === "add" ? t.bpmnDecisionAddTitle : t.bpmnDecisionEditTitle}
        </h2>
        <p className="text-sm leading-relaxed text-text-secondary">
          {fillTemplate(t.bpmnDecisionHelp, { min: String(MIN_BRANCHES), max: String(MAX_BRANCHES) })}
        </p>
        <label className="block text-sm text-text-secondary">
          {t.bpmnDecisionName}
          <input
            data-testid="bpmn-branch-name"
            value={name}
            maxLength={MAX_NAME_CHARS}
            onChange={(e) => setName(e.target.value.slice(0, MAX_NAME_CHARS))}
            autoComplete="off"
            required
            className="input-field mt-1 w-full"
          />
        </label>
        <ol className="space-y-2">
          {rows.map((r, i) => (
            <li key={r.key} className="rounded-lg border border-border p-2.5">
              <fieldset className="grid gap-2 sm:grid-cols-[1fr_12rem_auto] sm:items-end">
                <legend className="mb-1 text-xs font-medium text-text-muted">
                  {fillTemplate(t.bpmnDecisionBranch, { n: String(i + 1) })}
                </legend>
                <label className="block text-xs text-text-secondary">
                  {t.bpmnDecisionCondition}
                  <input
                    data-testid="bpmn-branch-condition"
                    value={r.condition}
                    maxLength={MAX_CONDITION_CHARS}
                    onChange={(e) => update(r.key, { condition: e.target.value.slice(0, MAX_CONDITION_CHARS) })}
                    autoComplete="off"
                    className="input-field mt-1 w-full"
                  />
                </label>
                <label className="block text-xs text-text-secondary">
                  {t.bpmnDecisionTarget}
                  <select
                    data-testid="bpmn-branch-target"
                    value={r.target}
                    onChange={(e) => update(r.key, { target: e.target.value })}
                    className="input-field mt-1 w-full"
                  >
                    {!r.target && <option value="" disabled />}
                    {r.target && !known.has(r.target) && <option value={r.target}>{r.target}</option>}
                    {steps.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name || s.id}
                      </option>
                    ))}
                    <option value={DECISION_END}>{t.bpmnDecisionEnd}</option>
                  </select>
                </label>
                <button
                  type="button"
                  className="icon-btn h-9 w-9 disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => setRows((current) => current.filter((x) => x.key !== r.key))}
                  disabled={rows.length <= MIN_BRANCHES}
                  aria-label={fillTemplate(t.bpmnDecisionRemoveBranch, { n: String(i + 1) })}
                  title={fillTemplate(t.bpmnDecisionRemoveBranch, { n: String(i + 1) })}
                  data-testid="bpmn-branch-remove"
                >
                  <Icon name="x" size={14} />
                </button>
              </fieldset>
            </li>
          ))}
        </ol>
        <button
          type="button"
          className="btn-secondary px-2.5 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-50"
          onClick={() => setRows((current) => [...current, row({ condition: "", target: "" })])}
          disabled={rows.length >= MAX_BRANCHES}
          data-testid="bpmn-branch-add"
        >
          <Icon name="plus" size={13} />
          {t.bpmnDecisionAddBranch}
        </button>
        {problem === "same_target" && (
          <p className="text-sm text-warning-text" data-testid="bpmn-branch-same-target">
            {t.bpmnDecisionSameTarget}
          </p>
        )}
        {error && (
          <p role="alert" className="text-sm text-danger-text">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={() => dialog.current?.close()} className="btn-secondary">
            {t.bpmnDecisionCancel}
          </button>
          <button
            type="submit"
            data-testid="bpmn-branch-save"
            disabled={Boolean(problem) || busy}
            className="btn-brand disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t.bpmnDecisionSave}
          </button>
        </div>
      </form>
    </dialog>
  );
}

/**
 * A rework or rejection path's name, condition and outcome: back to the step
 * it is on or an earlier one ("loop_to:<step id>"), or the end. Opened by a
 * step's "Add rework path" and by a path's Edit, prefilled then. Save hands
 * the values to `onSave`, which sends the operation through the canvas's one
 * gate; a refusal keeps the dialog open with what was typed, and `error`
 * says why.
 */
export function BpmnReworkDialog({
  mode,
  initial,
  steps,
  busy,
  error,
  onSave,
  onClose,
  t,
}: {
  mode: "add" | "edit";
  initial: ReworkValues;
  /** The steps the path can lead back to, in order; the end comes after them. */
  steps: { id: string; name: string }[];
  busy: boolean;
  error: string | null;
  /** True once the path is saved: the dialog closes then. */
  onSave: (values: ReworkValues) => Promise<boolean>;
  onClose: () => void;
  t: Dict;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [name, setName] = useState(initial.name);
  const [condition, setCondition] = useState(initial.condition);
  const [outcome, setOutcome] = useState(initial.outcome);

  useEffect(() => {
    const el = dialog.current;
    if (el && !el.open) el.showModal();
  }, []);

  const values: ReworkValues = { name, condition, outcome };
  const problem = reworkProblem(values);
  // An outcome the choices lack (an agent's loop to a later step, or to a step removed since) stays pickable as it is.
  const known = new Set([...steps.map((s) => `${REWORK_LOOP_TO}${s.id}`), REWORK_END]);

  async function save() {
    if (problem || busy) return;
    if (await onSave(values)) dialog.current?.close();
  }

  return (
    <dialog
      ref={dialog}
      onClose={onClose}
      aria-labelledby={titleId}
      data-testid="bpmn-rework-dialog"
      className="m-auto max-h-[calc(100dvh-2rem)] w-[min(30rem,calc(100vw-2rem))] overflow-y-auto rounded-lg border border-border bg-surface p-5 text-text shadow-lg backdrop:bg-black/40"
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <h2 id={titleId} className="text-base font-semibold text-text-strong">
          {mode === "add" ? t.bpmnReworkAddTitle : t.bpmnReworkEditTitle}
        </h2>
        <p className="text-sm leading-relaxed text-text-secondary">{t.bpmnReworkHelp}</p>
        <label className="block text-sm text-text-secondary">
          {t.bpmnReworkName}
          <input
            data-testid="bpmn-rework-name"
            value={name}
            maxLength={MAX_NAME_CHARS}
            onChange={(e) => setName(e.target.value.slice(0, MAX_NAME_CHARS))}
            autoComplete="off"
            required
            className="input-field mt-1 w-full"
          />
        </label>
        <label className="block text-sm text-text-secondary">
          {t.bpmnReworkCondition}
          <input
            data-testid="bpmn-rework-condition"
            value={condition}
            maxLength={MAX_CONDITION_CHARS}
            onChange={(e) => setCondition(e.target.value.slice(0, MAX_CONDITION_CHARS))}
            autoComplete="off"
            className="input-field mt-1 w-full"
          />
        </label>
        <label className="block text-sm text-text-secondary">
          {t.bpmnReworkOutcome}
          <select
            data-testid="bpmn-rework-outcome"
            value={outcome}
            onChange={(e) => setOutcome(e.target.value)}
            className="input-field mt-1 w-full"
          >
            {!outcome && <option value="" disabled />}
            {outcome && !known.has(outcome) && <option value={outcome}>{outcome}</option>}
            {steps.map((s) => (
              <option key={s.id} value={`${REWORK_LOOP_TO}${s.id}`}>
                {fillTemplate(t.bpmnReworkBackTo, { step: s.name || s.id })}
              </option>
            ))}
            <option value={REWORK_END}>{t.bpmnReworkEnd}</option>
          </select>
        </label>
        {error && (
          <p role="alert" className="text-sm text-danger-text">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={() => dialog.current?.close()} className="btn-secondary">
            {t.bpmnDecisionCancel}
          </button>
          <button
            type="submit"
            data-testid="bpmn-rework-save"
            disabled={Boolean(problem) || busy}
            className="btn-brand disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t.bpmnReworkSave}
          </button>
        </div>
      </form>
    </dialog>
  );
}
