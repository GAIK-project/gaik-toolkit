"use client";

import type { FieldSpec } from "@/components/field-schema-editor";
import { Icon } from "@/components/icons";
import { usePageSend } from "@/components/use-page-send";
import { askInChat } from "@/lib/chat-events";
import {
  buildReadableFields,
  extractionProposalHeading,
  type ExtractionProposal,
} from "@/lib/extraction-proposal";
import type { Dict } from "@/lib/i18n";
import type { TargetOutputSpec } from "@/lib/target-output-spec";

/**
 * Plain-language review of the extraction rules in the workspace (#251):
 * readable field names, examples and clear wording for missing values, with
 * technical identifiers, the raw prompt and Python definitions behind one
 * disclosure. Offers explicit Approve and Request changes actions while the
 * proposal awaits confirmation before schema generation.
 */
export function ExtractionProposalView({
  fields,
  targetOutputSpec,
  blueprintName,
  proposal,
  awaitingApproval,
  t,
}: {
  fields: FieldSpec[];
  targetOutputSpec?: TargetOutputSpec | null;
  blueprintName?: string;
  proposal?: ExtractionProposal | null;
  awaitingApproval: boolean;
  t: Dict;
}) {
  const L = t.extractionProposal;
  const { state, replying, send } = usePageSend();

  const heading = extractionProposalHeading(
    L,
    targetOutputSpec?.schemaName,
    blueprintName,
    proposal?.promptMarkdown,
  );
  const rows = buildReadableFields(fields, targetOutputSpec, proposal?.promptMarkdown, L);
  const hasTechnical =
    rows.length > 0 || Boolean(proposal?.promptMarkdown.trim()) || Boolean(proposal?.schemaCode?.trim());

  return (
    <section
      className="@container rounded-xl border border-border bg-surface"
      aria-labelledby="extraction-proposal-heading"
      data-testid="extraction-proposal"
    >
      <div className="px-4 py-4 sm:px-5">
        <h3 id="extraction-proposal-heading" className="text-base font-semibold text-text-strong">
          {heading}
        </h3>
      </div>

      {rows.length > 0 && (
        <ul className="divide-y divide-border border-t border-border" data-testid="extraction-proposal-fields">
          {rows.map((row) => (
            <li key={row.key} className="px-4 py-3 sm:px-5">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
                <span className="text-sm font-semibold text-text">{row.label}</span>
                <span className="ml-auto text-xs text-text-muted">
                  {t.planSchema.types[row.type]}
                  {row.required ? ` · ${t.planSchema.required}` : ""}
                </span>
              </div>
              {row.description && (
                <p className="mt-1 text-sm leading-relaxed text-text-secondary [overflow-wrap:anywhere]">
                  {row.description}
                </p>
              )}
              <dl className="mt-1.5 flex flex-wrap gap-x-5 gap-y-1 text-xs text-text-muted">
                {row.example && (
                  <div className="flex flex-wrap gap-1">
                    <dt className="font-medium text-text-secondary">{L.example}:</dt>
                    <dd className="[overflow-wrap:anywhere]">{row.example}</dd>
                  </div>
                )}
                {row.allowedValues && row.allowedValues.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    <dt className="font-medium text-text-secondary">{t.planSchema.allowed}</dt>
                    <dd className="[overflow-wrap:anywhere]">{row.allowedValues.join(", ")}</dd>
                  </div>
                )}
                <div className="flex flex-wrap gap-1">
                  <dt className="font-medium text-text-secondary">{L.missing}:</dt>
                  <dd className="[overflow-wrap:anywhere]">{row.missingText}</dd>
                </div>
              </dl>
            </li>
          ))}
        </ul>
      )}

      {hasTechnical && (
        <details className="group border-t border-border" data-testid="extraction-proposal-details">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 px-4 py-2.5 text-xs font-medium text-text-secondary transition-colors hover:text-text sm:px-5 [&::-webkit-details-marker]:hidden">
            <Icon
              name="chevronRight"
              size={13}
              className="transition-transform duration-150 ease-out group-open:rotate-90"
            />
            {L.technicalDetails}
          </summary>
          <div className="flex flex-col gap-3 border-t border-border bg-app/50 px-4 py-3 text-xs sm:px-5">
            {rows.length > 0 && (
              <div>
                <p className="mb-1.5 font-medium text-text-secondary">{L.technicalFieldId}</p>
                <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1">
                  {rows.map((row) => (
                    <div key={row.key} className="contents">
                      <dt className="font-mono text-text">{row.key}</dt>
                      <dd className="text-text-muted">
                        {t.planSchema.types[row.type]}
                        {row.required ? ` · ${t.planSchema.required}` : ""}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
            )}
            {proposal?.promptMarkdown.trim() && (
              <div>
                <p className="mb-1 font-medium text-text-secondary">{L.technicalPrompt}</p>
                <pre className="whitespace-pre-wrap break-words rounded-md border border-border bg-surface p-3 font-mono text-xs leading-relaxed text-text-secondary">
                  {proposal.promptMarkdown}
                </pre>
              </div>
            )}
            {proposal?.schemaCode?.trim() && (
              <div>
                <p className="mb-1 font-medium text-text-secondary">{L.technicalSchema}</p>
                <pre className="whitespace-pre-wrap break-words rounded-md border border-border bg-surface p-3 font-mono text-xs leading-relaxed text-text-secondary">
                  {proposal.schemaCode}
                </pre>
              </div>
            )}
          </div>
        </details>
      )}

      {awaitingApproval && (
        <div
          className="flex flex-wrap items-center gap-2 border-t border-border px-4 py-3 sm:px-5"
          data-testid="extraction-proposal-actions"
        >
          <button
            type="button"
            className="btn-secondary"
            disabled={state === "sent" || replying}
            onClick={() =>
              askInChat({
                key: "extraction-proposal",
                label: L.chip,
                prefix: L.requestPrefix,
              })
            }
          >
            <Icon name="messageSquareText" size={16} />
            {L.requestChanges}
          </button>
          <button
            type="button"
            className="btn-brand font-semibold"
            disabled={state === "sent" || replying}
            onClick={() => send(L.approveMessage)}
          >
            <Icon
              name={state === "sent" ? "loaderCircle" : "check"}
              size={16}
              className={state === "sent" ? "animate-spin" : ""}
            />
            {state === "sent" ? L.approving : L.approve}
          </button>
          {state === "failed" && (
            <p role="alert" className="w-full text-xs text-danger-text">
              {L.sendFailed}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
