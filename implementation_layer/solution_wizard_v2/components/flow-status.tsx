import { Icon } from "@/components/icons";
import { blueprintUpdateText, type BlueprintUpdate } from "@/lib/blueprint-update";
import type { Dict } from "@/lib/i18n";

/**
 * What the Workflow tab's two diagrams say the same way: the simple flow and
 * the BPMN editor are two views of one blueprint, so a lock or a version
 * written elsewhere reads the same on both.
 */

/**
 * Under the diagram after Gate 2: editing is off, why, and "Muokkaa" to open
 * it. One press opens both diagrams.
 */
export function FlowLockedNote({ onUnlock, testId, t }: { onUnlock: () => void; testId: string; t: Dict }) {
  return (
    <p
      className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1.5 border-t border-border bg-surface-muted/50 px-3 py-2 text-xs text-text-secondary"
      data-testid={`${testId}-locked`}
    >
      <span className="flex min-w-0 flex-1 basis-64 items-start gap-1.5">
        <Icon name="lock" size={13} className="mt-0.5 text-text-muted" />
        <span>{t.flowLocked}</span>
      </span>
      <button
        type="button"
        className="btn-secondary px-2.5 py-1 text-xs"
        onClick={onUnlock}
        data-testid={`${testId}-unlock`}
      >
        <Icon name="pencil" size={13} />
        {t.planEdit}
      </button>
    </p>
  );
}

/**
 * Under the BPMN editor while it can be edited: what saves by itself, what
 * waits for "Tallenna muutokset", and when the wizard hears of a save. After
 * Gate 2, where "Muokkaa kaaviota" opened it, "Lopeta muokkaus" closes it
 * again; unsaved edits are saved or discarded first, so the button waits.
 * Before this the lock note went away for good, with no word on how edits
 * are kept and no way back to the read-only view.
 */
export function FlowEditingNote({
  help,
  onLock,
  lockWaits = false,
  testId,
  t,
}: {
  help: string;
  /** Closes the diagram for edits again; without it there is no lock to go back to. */
  onLock?: () => void;
  /** There are edits a save or a discard has to settle first. */
  lockWaits?: boolean;
  testId: string;
  t: Dict;
}) {
  return (
    <p
      className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1.5 border-t border-border bg-surface-muted/50 px-3 py-2 text-xs text-text-secondary"
      data-testid={`${testId}-editing`}
    >
      <span className="flex min-w-0 flex-1 basis-64 items-start gap-1.5">
        <Icon name="pencil" size={13} className="mt-0.5 text-text-muted" />
        <span>{help}</span>
      </span>
      {onLock && (
        <button
          type="button"
          className="btn-secondary px-2.5 py-1 text-xs"
          onClick={onLock}
          disabled={lockWaits}
          title={lockWaits ? t.flowEditDoneWaits : undefined}
          data-testid={`${testId}-lock`}
        >
          <Icon name="lock" size={13} />
          {t.flowEditDone}
        </button>
      )}
    </p>
  );
}

/**
 * The status line of a diagram drawn again from a version this panel did not
 * save: the wizard's, from the chat, or one written in another window.
 */
export function FlowUpdatedLine({ update, testId, t }: { update: BlueprintUpdate; testId: string; t: Dict }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-text-secondary" data-testid={testId}>
      <Icon
        name={update.fromChat ? "messageSquareText" : "history"}
        size={14}
        className={update.fromChat ? "text-brand-text" : "text-text-muted"}
      />
      {blueprintUpdateText(update, t)}
    </span>
  );
}
