"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { StepType } from "@/lib/blueprint-ops";
import { fillTemplate } from "@/lib/chat-template";
import type { Dict } from "@/lib/i18n";
import {
  MAX_STEP_DESCRIPTION,
  MAX_STEP_NAME,
  PAGE_TYPE,
  STEP_OP_TYPES,
  type PanelFields,
  type PanelValues,
} from "@/lib/step-panel-model";
import { stepTypeLabels } from "@/components/step-type";
import { Icon } from "@/components/icons";

/** A field of the panel; read-only, it looks so. */
const FIELD = "input-field w-full text-sm disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-text-secondary disabled:hover:border-border-strong";

/**
 * A step's name, description and type, beside the BPMN canvas. A field saves
 * when the user leaves it or presses Enter (Shift+Enter is a new line in the
 * description), and Escape takes its change back; the type saves when it is
 * picked. Each save hands the panel's values to `onSave`, which sends what
 * changed as one edit (lib/step-panel-model `panelOps`). The lane (who does
 * the step) saves when it is picked, through `onLaneChange`; the select is
 * there only where the editor knows the lanes.
 *
 * What the user typed stays in its field until the step has it: through an
 * edit on its way, and over a refusal, so nothing typed is lost; once the
 * edit is made the field shows the step's own text again. `disabled`
 * while an edit is on its way and while the canvas is read-only.
 */
export function BpmnStepPanel({
  fields,
  disabled,
  onSave,
  lanes = null,
  lane = "",
  onLaneChange,
  t,
}: {
  fields: PanelFields;
  disabled: boolean;
  /** Sends what changed; true once it is made (or there was nothing to change). */
  onSave: (after: PanelValues) => Promise<boolean>;
  /** The lanes a step can be put in (participant id and name); null hides the select. */
  lanes?: { id: string; name: string }[] | null;
  /** The lane the step is put in; "" when its type decides. */
  lane?: string;
  /** A lane picked: its id, or null for the lane of the step's type. */
  onLaneChange?: (laneId: string | null) => Promise<boolean>;
  t: Dict;
}) {
  const descriptionId = useId();
  const countId = useId();
  // What is typed and not yet the step's: null when the field shows the step's own text.
  const [name, setNameState] = useState<string | null>(null);
  const [description, setDescriptionState] = useState<string | null>(null);
  const typed = useRef<{ name: string | null; description: string | null }>({ name: null, description: null });
  function setName(next: string | null) {
    typed.current.name = next;
    setNameState(next);
  }
  function setDescription(next: string | null) {
    typed.current.description = next;
    setDescriptionState(next);
  }

  // Once the step has what was typed (saved, or written so elsewhere), the field follows the step again.
  useEffect(() => {
    if (typed.current.name !== null && typed.current.name.trim() === fields.name.trim()) setName(null);
  }, [fields.name]);
  useEffect(() => {
    const text = typed.current.description;
    if (text !== null && text.trim().slice(0, MAX_STEP_DESCRIPTION) === fields.description.trim()) {
      setDescription(null);
    }
  }, [fields.description]);

  function values(type: StepType = fields.type): PanelValues {
    return {
      stepId: fields.stepId,
      name: typed.current.name ?? fields.name,
      description: typed.current.description ?? fields.description,
      type,
    };
  }

  /** Sends the panel's values; once made, the fields show the step's own text again. */
  async function send(sent: PanelValues) {
    const before = { ...typed.current };
    if (!(await onSave(sent))) return;
    // What was typed after the save started stays for the next one.
    if (typed.current.name === before.name) setName(null);
    if (typed.current.description === before.description) setDescription(null);
  }

  function save() {
    if (disabled) return;
    if (typed.current.name === null && typed.current.description === null) return;
    void send(values());
  }

  const labels = stepTypeLabels(t);
  const shownDescription = description ?? fields.description;

  return (
    <div className="flex flex-col gap-2.5" data-testid="bpmn-step-panel">
      {/* Name and type side by side where the panel spans a narrow canvas, so it covers less of it. */}
      <div className="grid grid-cols-2 gap-2 @lg:grid-cols-1 @lg:gap-2.5">
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-text-muted">{t.wsBpmnPropertiesName}</span>
          <input
            type="text"
            className={FIELD}
            value={name ?? fields.name}
            maxLength={MAX_STEP_NAME}
            disabled={disabled}
            title={t.bpmnStepSaveHint}
            onChange={(e) => setName(e.target.value)}
            onBlur={save}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                save();
              } else if (e.key === "Escape") {
                e.preventDefault();
                setName(null);
              }
            }}
            data-testid="bpmn-property-name"
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-text-muted">{t.wsBpmnPropertiesType}</span>
          <select
            className={FIELD}
            value={fields.type}
            disabled={disabled}
            onChange={(e) => {
              if (!disabled) void send(values(e.target.value as StepType));
            }}
            data-testid="bpmn-step-type"
          >
            {STEP_OP_TYPES.map((type) => (
              <option key={type} value={type}>
                {labels[PAGE_TYPE[type]]}
              </option>
            ))}
          </select>
        </label>
      </div>

      {lanes && lanes.length > 0 && onLaneChange && (
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-text-muted">{t.bpmnStepLane}</span>
          <select
            className={FIELD}
            value={lane}
            disabled={disabled}
            onChange={(e) => {
              if (!disabled) void onLaneChange(e.target.value || null);
            }}
            data-testid="bpmn-step-lane"
          >
            <option value="">{t.bpmnStepLaneDefault}</option>
            {lanes.map((option) => (
              <option key={option.id} value={option.id}>
                {option.name}
              </option>
            ))}
            {lane && !lanes.some((option) => option.id === lane) && <option value={lane}>{lane}</option>}
          </select>
        </label>
      )}

      <div className="flex flex-col gap-1.5">
        <div className="flex items-baseline justify-between gap-2">
          <label htmlFor={descriptionId} className="text-xs font-medium text-text-muted">
            {t.bpmnStepDescription}
          </label>
          <span id={countId} className="text-[11px] tabular-nums text-text-muted" data-testid="bpmn-step-description-count">
            {fillTemplate(t.bpmnStepDescriptionCount, {
              n: String(shownDescription.length),
              max: String(MAX_STEP_DESCRIPTION),
            })}
          </span>
        </div>
        <textarea
          id={descriptionId}
          className={`${FIELD} min-h-[3.5rem] resize-y`}
          rows={2}
          value={shownDescription}
          maxLength={MAX_STEP_DESCRIPTION}
          disabled={disabled}
          title={t.bpmnStepSaveHint}
          aria-describedby={countId}
          onChange={(e) => setDescription(e.target.value.slice(0, MAX_STEP_DESCRIPTION))}
          onBlur={save}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              save();
            } else if (e.key === "Escape") {
              e.preventDefault();
              setDescription(null);
            }
          }}
          data-testid="bpmn-step-description"
        />
      </div>

      {fields.needsComponent && (
        <p className="flex items-start gap-1.5 text-xs text-warning-text" data-testid="bpmn-step-needs-component">
          <Icon name="info" size={13} className="mt-px shrink-0" />
          <span>{t.bpmnStepNeedsComponent}</span>
        </p>
      )}
    </div>
  );
}
