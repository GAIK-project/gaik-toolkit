"use client";

import { useEffect, useId, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { approve } from "@/app/(app)/sessions/[id]/actions";
import { askInChat, CHAT_REPLYING_EVENT, GATE_BAR_ATTRIBUTE, GATE_POINT_EVENT } from "@/lib/chat-events";
import { fillTemplate } from "@/lib/chat-template";
import { gateReference } from "@/lib/gate-guide";
import { gate3Waits, packageReadFor, resultStaleFor, subscribeResultStale } from "@/lib/poc-result-state";
import { PendingSubmitButton } from "./pending-submit-button";
import { Icon } from "./icons";

/** How long the approve button stays marked after "Show me" in the chat. */
const POINTED_MS = 1500;

export type GateDecisionLabels = {
  /** The gate's own approve label ("Hyväksy ratkaisun rakenne ja jatka"). */
  approve: string;
  /** What the approve button shows where the full label does not fit ("Hyväksy"). */
  approveShort: string;
  approving: string;
  /** One line on what approving leads to. */
  note: string;
  requestChanges: string;
  /** Each gate's business topic, Gate 1–4, for the chat reference. */
  topics: string[];
  chip: string;
  requestPrefix: string;
  /** Said above the buttons while the gate stands rejected. */
  rejected: string;
  /** Said above the buttons at Gate 3 while the test result is an earlier package's. */
  staleResult: string;
  /** Compact dismissible action panel controls (#251). */
  dismissPanel?: string;
  showPanel?: string;
  waitingPanel?: string;
};

/**
 * The decision at a gate, kept in view under what it decides: ask for changes
 * in the chat, or approve.
 *
 * Approval is the server action it always was (agent_busy, gate_not_ready and
 * the wake turn stay as they are). A change request opens the chat with the
 * gate as a reference, so it becomes a real turn the agent acts on. The bar
 * has no reject button: a rejection said nothing a change request does not. A
 * gate that already stands rejected (an older session, or the API) is still
 * shown as such, and the same two buttons are its way on.
 *
 * Gate 3 approves a test run. While the result on the PoC tab is, or may be,
 * that of an earlier package (the wizard is replying, or has changed the
 * package since the run), the approval waits and the bar says why
 * (lib/poc-result-state). The page says so from wizard_api's own record
 * (`packageChanged`), which holds on every tab and after a reload; the PoC
 * tab says so from what it has seen since.
 */
export function GateDecisionBar({
  sessionId,
  gate,
  gateStep,
  rejected = false,
  blocked = false,
  missing,
  hadNotice = false,
  packageChanged = false,
  placement = "bottom",
  dismissible = false,
  labels,
}: {
  sessionId: string;
  /** Gate 1–4. */
  gate: number;
  gateStep: number;
  /** The gate stands rejected: say so above the buttons. */
  rejected?: boolean;
  /** Approval is not possible yet (Gate 1 without the business context). */
  blocked?: boolean;
  /** Why it is blocked and the fields that unblock it, shown above the buttons. */
  missing?: ReactNode;
  /** The page shows a notice from a refused action; the next action clears it. */
  hadNotice?: boolean;
  /** As the page read it: the package has changed since the test run that passed. */
  packageChanged?: boolean;
  /** "top" places the compact panel right beside/above the structure being reviewed (#251). */
  placement?: "bottom" | "top";
  /** Allows collapsing the panel out of the way while keeping actions reachable (#251). */
  dismissible?: boolean;
  labels: GateDecisionLabels;
}) {
  const noteId = useId();
  const staleId = useId();
  const [dismissed, setDismissed] = useState(false);
  const resultStale = useSyncExternalStore(
    subscribeResultStale,
    () => resultStaleFor(sessionId),
    () => false,
  );
  const packageRead = useSyncExternalStore(
    subscribeResultStale,
    () => packageReadFor(sessionId),
    () => false,
  );
  const stale = gate === 3 && gate3Waits({ stale: resultStale, packageRead }, packageChanged);
  // The wizard's reply at a gate ends with "approve it in the panel". The
  // approve button draws the eye once as the bar appears, and again each time
  // the wizard finishes a reply while the session waits here.
  const [nudge, setNudge] = useState(1);
  useEffect(() => {
    let replying = false;
    const onReplying = (e: Event) => {
      const now = Boolean((e as CustomEvent<boolean>).detail);
      if (replying && !now) setNudge((n) => n + 1);
      replying = now;
    };
    window.addEventListener(CHAT_REPLYING_EVENT, onReplying);
    return () => window.removeEventListener(CHAT_REPLYING_EVENT, onReplying);
  }, []);

  // "Show me" in the chat (GATE_POINT_EVENT): the bar comes into view, the
  // approve button takes the focus and wears a ring for a moment. With reduced
  // motion there is no ring and no smooth scroll, only the place and the focus.
  const rootRef = useRef<HTMLDivElement>(null);
  const [pointed, setPointed] = useState(false);
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const onPoint = () => {
      setDismissed(false);
      requestAnimationFrame(() => {
        const root = rootRef.current;
        if (!root) return;
        const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        root.scrollIntoView({ block: "nearest", behavior: still ? "auto" : "smooth" });
        root.querySelector<HTMLButtonElement>('button[type="submit"]')?.focus({ preventScroll: true });
        setPointed(true);
        clearTimeout(timer);
        timer = setTimeout(() => setPointed(false), POINTED_MS);
      });
    };
    window.addEventListener(GATE_POINT_EVENT, onPoint);
    return () => {
      clearTimeout(timer);
      window.removeEventListener(GATE_POINT_EVENT, onPoint);
    };
  }, []);

  const edge = placement === "top" ? "border-b border-border bg-surface-muted/40 py-2" : "border-t border-border bg-surface py-3";
  const topic = labels.topics[gate - 1] ?? "";

  if (dismissible && dismissed) {
    return (
      <div
        ref={rootRef}
        {...{ [GATE_BAR_ATTRIBUTE]: "" }}
        data-testid={`gate${gate}-actions-collapsed`}
        className={`relative z-10 flex shrink-0 items-center justify-between gap-2 px-4 sm:px-6 ${edge}`}
      >
        <span className="truncate text-xs font-medium text-text-secondary">
          {labels.waitingPanel ? fillTemplate(labels.waitingPanel, { topic }) : topic}
        </span>
        <button
          type="button"
          onClick={() => setDismissed(false)}
          data-testid="gate-panel-restore"
          className="btn-inline shrink-0 text-xs font-medium text-brand-text"
        >
          {labels.showPanel ?? labels.approveShort}
        </button>
      </div>
    );
  }

  return (
    <div
      ref={rootRef}
      {...{ [GATE_BAR_ATTRIBUTE]: "" }}
      data-testid={`gate${gate}-actions`}
      className={`@container relative z-10 shrink-0 px-4 sm:px-6 ${edge}`}
    >
      {missing}
      {rejected && (
        <p role="status" className="mb-2.5 flex items-start gap-2 text-sm text-danger-text">
          <Icon name="circleAlert" size={16} className="mt-0.5" />
          <span>{labels.rejected}</span>
        </p>
      )}
      {stale && (
        <p
          id={staleId}
          role="status"
          data-testid="gate-stale-result"
          className="mb-2.5 flex items-start gap-2 text-sm text-warning-text"
        >
          <Icon name="circleAlert" size={16} className="mt-0.5 shrink-0" />
          <span>{labels.staleResult}</span>
        </p>
      )}

      {/* One row at every width, in reading order: ask for changes, approve.
          On a phone approve reads "Hyväksy" (its full label stays its name).
          The note is the approve button's description and its hover hint; it
          is written out only where the row has room for it on the left. Under
          the row it cost a line of the workspace's height at every usual
          width. */}
      <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 @xl:gap-x-2">
        <button
          type="button"
          onClick={() =>
            askInChat(
              gateReference(
                { topics: labels.topics, chip: labels.chip, prefix: labels.requestPrefix },
                gate,
                gateStep,
              ),
            )
          }
          className="btn-secondary @max-xl:px-3 @xl:ml-auto @5xl:order-2 @5xl:ml-0"
        >
          <Icon name="messageSquareText" size={16} className="@max-xl:hidden" />
          {labels.requestChanges}
        </button>
        <form
          // Keyed so the highlight plays again on the next nudge.
          key={nudge}
          action={approve}
          title={labels.note}
          data-pointed={pointed ? "" : undefined}
          className={`gate-point min-w-0 flex-1 rounded-md @xl:flex-none @5xl:order-3 ${blocked || stale ? "" : "gate-nudge"}`}
        >
          <input type="hidden" name="id" value={sessionId} />
          <input type="hidden" name="step" value={gateStep} />
          {hadNotice && <input type="hidden" name="notice" value="1" />}
          <PendingSubmitButton
            label={
              <>
                <span className="@xl:hidden" aria-hidden>
                  {labels.approveShort}
                </span>
                <span className="@max-xl:sr-only">{labels.approve}</span>
              </>
            }
            pendingLabel={
              <>
                <span className="@xl:hidden" aria-hidden>
                  {labels.approveShort}
                </span>
                <span className="@max-xl:sr-only">{labels.approving}</span>
              </>
            }
            disabled={blocked || stale}
            icon="check"
            // Why it waits, while it does; else what approving leads to.
            describedBy={stale ? staleId : noteId}
            className="btn-brand w-full whitespace-nowrap font-semibold"
          />
        </form>
        {dismissible && labels.dismissPanel && (
          <button
            type="button"
            onClick={() => setDismissed(true)}
            aria-label={labels.dismissPanel}
            title={labels.dismissPanel}
            data-testid="gate-panel-dismiss"
            className="icon-btn h-8 w-8 shrink-0 @5xl:order-4"
          >
            <Icon name="x" size={15} />
          </button>
        )}
        {/* On a phone the line under the phase title says what to do; the
            note stays the approve button's description. */}
        <p
          id={noteId}
          className="sr-only text-xs text-text-muted @5xl:not-sr-only @5xl:order-1 @5xl:basis-0 @5xl:flex-1 @5xl:text-left"
        >
          {labels.note}
        </p>
      </div>
    </div>
  );
}
