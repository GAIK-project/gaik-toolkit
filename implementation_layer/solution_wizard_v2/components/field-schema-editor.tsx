"use client";

import { useState } from "react";
import type { Dict } from "@/lib/i18n";
import { fillTemplate } from "@/lib/chat-template";

// The specification step's view: the output fields the wizard and the user
// have agreed (the draft blueprint's `target_output_spec`, #141), one row per
// field. A row says the field's name, its type and whether it is required; the
// rest of the selected field (its rule, allowed values, what happens when the
// value is missing) stands beside the list where the view is wide and under
// the field's own row where it is narrow. Read-only: a change goes through the
// chat. The same fields are listed on the Blueprint tab later
// (components/solution-plan-view), in the same words for a type.

export type FieldSpec = {
  name: string;
  type: "text" | "enum" | "date" | "number" | "boolean";
  allowedValues?: string[];
  required: boolean;
  missingBehavior: "empty" | "default";
  defaultValue?: string;
  rule?: string;
};

/** What a row does not say: the rule, the allowed values and the missing-value behaviour. */
function FieldDetail({ field, labels }: { field: FieldSpec; labels: Dict["specFields"] }) {
  const term = "text-xs font-medium text-text-muted";
  const missing =
    field.missingBehavior === "empty"
      ? labels.leftEmpty
      : field.defaultValue
        ? fillTemplate(labels.defaultValue, { value: field.defaultValue })
        : labels.noDefault;
  return (
    <dl className="space-y-3 text-sm">
      {field.rule && (
        <div>
          <dt className={term}>{labels.rule}</dt>
          <dd className="text-text-secondary [overflow-wrap:anywhere]">{field.rule}</dd>
        </div>
      )}
      {field.allowedValues && field.allowedValues.length > 0 && (
        <div>
          <dt className={term}>{labels.allowed}</dt>
          <dd className="text-text [overflow-wrap:anywhere]">{field.allowedValues.join(", ")}</dd>
        </div>
      )}
      <div>
        <dt className={term}>{labels.missing}</dt>
        <dd className="text-text [overflow-wrap:anywhere]">{missing}</dd>
      </div>
    </dl>
  );
}

export function FieldSchemaEditor({ fields = [], t }: { fields?: FieldSpec[]; t: Dict }) {
  const L = t.specFields;
  const [sel, setSel] = useState(0);
  // The list can get shorter under the selection when the wizard drops a field.
  const selected = Math.min(sel, fields.length - 1);
  const field = fields[selected];

  return (
    // A container of its own: the detail goes beside the list by the room this
    // view has, which the chat docked beside it changes, not by the window's width.
    <div className="@container mx-auto w-full max-w-4xl" data-testid="spec-fields">
      <h3 className="text-base font-semibold text-text">{L.title}</h3>

      {!field ? (
        <p className="mt-2 text-sm text-text-muted" data-testid="spec-fields-empty">
          {L.empty}
        </p>
      ) : (
        <div className="mt-3 grid gap-x-8 @2xl:grid-cols-[minmax(0,1fr)_17rem]">
          <ul className="divide-y divide-border border-y border-border">
            {fields.map((row, i) => {
              const current = i === selected;
              return (
                <li key={row.name}>
                  <button
                    type="button"
                    onClick={() => setSel(i)}
                    aria-current={current ? "true" : undefined}
                    className={`grid w-full grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-4 px-3 py-2.5 text-left ${
                      current ? "bg-surface-muted" : "hover:bg-surface-muted/60"
                    }`}
                  >
                    <span className="break-words font-mono text-[13px] text-text">{row.name}</span>
                    <span className="text-right text-xs text-text-secondary">
                      {t.planSchema.types[row.type]}
                      {row.required && <span className="text-text-muted"> · {t.planSchema.required}</span>}
                    </span>
                  </button>
                  {/* Narrow: the field's detail opens under its own row. */}
                  {current && (
                    <div className="px-3 pb-3 pt-1 @2xl:hidden">
                      <FieldDetail field={row} labels={L} />
                    </div>
                  )}
                </li>
              );
            })}
          </ul>

          {/* Wide: the same detail beside the list, in view while the list scrolls with the page. */}
          <section
            aria-labelledby="spec-field-name"
            className="sticky top-0 hidden self-start border-l border-border py-2.5 pl-6 @2xl:block"
          >
            <h4 id="spec-field-name" className="break-words font-mono text-[13px] font-semibold text-text">
              {field.name}
            </h4>
            <div className="mt-3">
              <FieldDetail field={field} labels={L} />
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
