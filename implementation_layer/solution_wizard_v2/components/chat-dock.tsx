"use client";

import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import type { ChatMessage, PendingTurn } from "@/lib/mock-sessions";
import { ChatPanel, type ChatGateAction } from "./chat-panel";
import { Icon } from "./icons";
import type { ChatActivityLabels } from "@/lib/chat-activity";
import type { ChatErrorLabels } from "@/lib/chat-limits";
import {
  CHAT_REFERENCE_EVENT,
  CHAT_SEND_EVENT,
  type ChatReference,
  type QueuedMessage,
} from "@/lib/chat-events";
import { takeChatReference } from "@/lib/case-chat";
import { approvedGateIn, asChatReference } from "@/lib/chat-reference";
import { GATE_STEPS } from "@/lib/wizard-state-machine";
import { dropFirstMessage, pendingFirstMessage, type PendingFirstMessage } from "@/lib/first-message";
import { withoutStartLines } from "@/lib/chat-background";
import { GLIDE_EASING } from "@/lib/motion";
import type { ChatQuestionLabels } from "./chat-questions";

/** The width a viewer last dragged the chat to; a per-browser convenience. */
const WIDTH_KEY = "gaik-wizard.chat-width";
const DEFAULT_WIDTH = 400;
/** While the chat is the focus (requirements gathering) it starts wider. */
const WIDE_WIDTH = 480;
const MIN_WIDTH = 320;
const MAX_WIDTH = 720;
/** The workspace keeps at least this much when the chat is dragged wider. */
const MIN_WORKSPACE = 440;
const KEY_STEP = 24;
/** How long the chat takes to move to its side when the workspace arrives. */
const DOCK_MOVE_MS = 320;

/** Opens the chat from elsewhere on the page (the "start" button of the first step). */
export const OPEN_CHAT_EVENT = "gaik-wizard:open-chat";

export function ChatDock({
  sessionId,
  initialMessages,
  chatTitle,
  greeting,
  aiNotice,
  assistantLabel,
  inputPlaceholder,
  inputLabel,
  sendLabel,
  streamFailedLabel,
  thinkingLabel,
  startingLabel,
  wizardLive,
  hideChatLabel,
  showChatLabel,
  resizeLabel,
  defaultOpen = true,
  wide = false,
  lead = false,
  leadHeader,
  autoSend,
  busyLabel,
  activityLabels,
  errorLabels,
  questionLabels,
  pendingTurn = null,
  gateAction,
}: {
  sessionId: string;
  initialMessages: ChatMessage[];
  chatTitle: string;
  greeting: string;
  aiNotice: string;
  assistantLabel: string;
  inputPlaceholder: string;
  inputLabel: string;
  sendLabel: string;
  streamFailedLabel: string;
  thinkingLabel: string;
  /** In its place while the wizard is being started (lib/wizard-start). */
  startingLabel?: string;
  /** Whether a wizard is held for the session, as the page read it. */
  wizardLive?: boolean | null;
  hideChatLabel: string;
  showChatLabel: string;
  /** Accessible name of the drag handle between the workspace and the chat. */
  resizeLabel: string;
  /** false on BPMN+ workspace steps so the canvas gets the viewport (GAIK review). */
  defaultOpen?: boolean;
  /** wider panel while the chat is the focus (gathering / Q&A). */
  wide?: boolean;
  /** The chat is the page's main content (lib/session-start): it fills the
   *  space beside the steps instead of docking, and cannot be closed. */
  lead?: boolean;
  /** What the page shows above the chat while it leads: the steps on a
   *  narrow screen and the page's notices. */
  leadHeader?: ReactNode;
  /** A message the panel sends on its own once (a gate approved in the panel, #173). */
  autoSend?: string;
  /** Shown when the wizard is still answering the previous message. */
  busyLabel: string;
  activityLabels?: ChatActivityLabels;
  errorLabels?: ChatErrorLabels;
  /** Labels for answering a round of questions one by one. */
  questionLabels?: ChatQuestionLabels;
  /** The message the wizard is answering as the page loads (a reload mid-reply). */
  pendingTurn?: PendingTurn | null;
  /** The gate decision the session waits for, offered under the wizard's newest reply. */
  gateAction?: ChatGateAction;
}) {
  // The step decides whether the dock opens, once. A chat turn can move the
  // step (the page re-renders after every turn), and following the new default
  // then collapsed the dock under the message just sent: the input vanished
  // mid-conversation. The page keys this dock by session, so another session
  // still opens with its own default. The width does follow the step (wider
  // while gathering requirements) until the viewer sets one.
  // A page loaded in the middle of a reply opens on it: the reply is where
  // the session is.
  const [open, setOpen] = useState(defaultOpen || Boolean(pendingTurn));
  const [width, setWidth] = useState(wide ? WIDE_WIDTH : DEFAULT_WIDTH);
  // The width the viewer chose, or the step's default until they do; a
  // narrower window clamps what is shown, and a wider one gives it back.
  const preferredWidth = useRef(width);
  const userWidth = useRef(false);
  // The widest the separator can go in this window, for assistive tech.
  const [maxWidth, setMaxWidth] = useState(MAX_WIDTH);
  const [dragging, setDragging] = useState(false);
  // Bumped to move focus into the message field (the first step's start button).
  const [focusSignal, setFocusSignal] = useState(0);
  // Messages handed over by CHAT_SEND_EVENT, in order, until the panel takes
  // them. Kept here because the panel unmounts when the dock collapses; a
  // message the panel has taken is gone from here, so reopening the chat does
  // not send it again.
  const [queue, setQueue] = useState<QueuedMessage[]>([]);
  // A reply is arriving. The panel holds the conversation, so a chat closed
  // in the middle of a reply keeps its panel, out of sight, until the reply
  // is whole: opened again, the chat shows the message and its reply.
  const [replying, setReplying] = useState(Boolean(pendingTurn));
  const queuedCount = useRef(0);
  // The item on the page the next message is about (CHAT_REFERENCE_EVENT),
  // shown as a chip above the field until it is sent or removed. Kept here, as
  // the half-typed message is, because the panel unmounts when the dock collapses.
  const [reference, setReference] = useState<ChatReference | null>(null);
  const lastDraft = useRef<string | null>(null);
  // The reference the case page kept for this session, taken once (lib/case-chat).
  const keptReference = useRef<ChatReference | null | undefined>(undefined);
  // The message that started this session on the start view (lib/first-message),
  // read once; undefined until it has been looked for.
  const handedOver = useRef<PendingFirstMessage | null | undefined>(undefined);
  // Where the start view's field stood when that message was sent, in px from
  // the window's top; null when the session was not opened that way.
  const [arrivedFrom, setArrivedFrom] = useState<number | null>(null);
  // While gathering requirements the chat is where the session happens, so it
  // stays open on a narrow screen too, and an empty one takes the cursor.
  const startsInChat = useRef(wide);
  const startsEmpty = useRef(initialMessages.length === 0);
  // Kept here (not in ChatPanel) so a half-typed message survives hide/show —
  // ChatPanel unmounts when the dock collapses to the rail.
  const [chatInput, setChatInput] = useState("");
  const panelId = useId();
  const asideRef = useRef<HTMLDivElement>(null);
  // Focus follows the panel: opening puts it in the message field, closing
  // puts it back on the rail's open button (the header button it was on is
  // gone with the panel).
  const railToggleRef = useRef<HTMLButtonElement>(null);
  const focusRailOnClose = useRef(false);
  useEffect(() => {
    if (open || !focusRailOnClose.current) return;
    focusRailOnClose.current = false;
    railToggleRef.current?.focus();
  }, [open]);
  // Below 1280 px the open chat lies over the workspace: Esc closes it and
  // puts focus back on the button that opened it.
  useEffect(() => {
    // The chat that is the page has nothing behind it to go back to.
    if (!open || lead) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      if (!window.matchMedia("(max-width: 1279px)").matches) return;
      // An Esc meant for a dialog or the BPMN editor is theirs, not the chat's.
      const target = e.target;
      if (!(target instanceof Node) || !asideRef.current?.contains(target)) return;
      // The full-size diagram is a dialog inside the chat: its Esc closes it, not the chat.
      if (target instanceof Element && target.closest("dialog[open]")) return;
      setOpen(false);
      document.querySelector<HTMLElement>("[data-open-chat]")?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, lead]);
  // The running drag's cleanup, so leaving the page mid-drag still restores
  // text selection and drops the listeners.
  const endDragRef = useRef<(() => void) | null>(null);
  useEffect(() => () => endDragRef.current?.(), []);

  // Widest the chat may go without squeezing the workspace below its minimum.
  const clamp = useCallback((w: number) => {
    const aside = asideRef.current;
    const main = aside?.previousElementSibling as HTMLElement | null;
    const roomy = aside && main ? aside.offsetWidth + main.offsetWidth - MIN_WORKSPACE : MAX_WIDTH;
    const max = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, roomy));
    return Math.round(Math.min(Math.max(w, MIN_WIDTH), max));
  }, []);

  useEffect(() => {
    try {
      const saved = Number(window.localStorage.getItem(WIDTH_KEY));
      if (saved > 0) {
        preferredWidth.current = saved;
        userWidth.current = true;
        setWidth(clamp(saved));
      }
    } catch {
      // Storage blocked: the default width stands.
    }
    // Below 1280 px a docked chat squeezed the workspace to a third of the
    // screen; there it opens over the workspace instead, so it starts closed
    // and opens from its button.
    if (window.matchMedia("(max-width: 1279px)").matches) {
      if (!startsInChat.current) setOpen(false);
    }
    else setMaxWidth(clamp(MAX_WIDTH));
    // Below 1280 px the dock is an overlay or hidden, so there is nothing to
    // measure against; the docked width is worked out again above it.
    const onResize = () => {
      if (window.innerWidth < 1280) return;
      setWidth(clamp(preferredWidth.current));
      setMaxWidth(clamp(MAX_WIDTH));
    };
    window.addEventListener("resize", onResize);
    // The room also changes without the window: the sidebar folds or opens
    // beside the session, and the chat must not keep a width that squeezes
    // the workspace under its minimum.
    const row = asideRef.current?.parentElement;
    const room =
      row && typeof ResizeObserver === "function" ? new ResizeObserver(onResize) : null;
    if (row) room?.observe(row);
    return () => {
      window.removeEventListener("resize", onResize);
      room?.disconnect();
    };
  }, [clamp]);

  // The chat that was the page docks beside the workspace. That one change is
  // shown as a movement, so the reader sees where the conversation went: the
  // workspace comes in from the left and the chat glides from the middle of
  // the page to its side. Before the paint, so the docked layout is never seen
  // standing still first. Every other page update stays as it is.
  const wasLead = useRef(lead);
  useLayoutEffect(() => {
    const before = wasLead.current;
    wasLead.current = lead;
    if (lead || !before) return;
    const dock = asideRef.current;
    const workspace = dock?.previousElementSibling;
    const docked = window.innerWidth >= 1280;
    if (
      dock &&
      workspace instanceof HTMLElement &&
      typeof dock.animate === "function" &&
      !window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      const timing: KeyframeAnimationOptions = { duration: DOCK_MOVE_MS, easing: GLIDE_EASING };
      // Measured before either of them moves.
      const from = workspace.getBoundingClientRect();
      const to = dock.getBoundingClientRect();
      workspace.animate(
        [{ opacity: 0, transform: "translateX(-24px)" }, { opacity: 1, transform: "none" }],
        timing,
      );
      // Below the desktop layout the chat is a sheet or a panel over the
      // workspace, which has its own way in.
      if (docked) {
        // The middle of the space the chat filled, against its middle now.
        const shift = (from.left + to.right) / 2 - (to.left + to.width / 2);
        dock.animate([{ transform: `translateX(${shift}px)` }, { transform: "none" }], timing);
      }
    }
    // The width the dock takes is measured against the workspace, which was
    // not there to measure before.
    if (docked) {
      setWidth(clamp(preferredWidth.current));
      setMaxWidth(clamp(MAX_WIDTH));
    }
  }, [lead, clamp]);

  // Until the viewer sets a width, the dock takes the step's default: wide while
  // gathering requirements, narrower once the blueprint, BPMN and PoC take over.
  useEffect(() => {
    if (userWidth.current) return;
    const w = wide ? WIDE_WIDTH : DEFAULT_WIDTH;
    preferredWidth.current = w;
    setWidth(clamp(w));
  }, [wide, clamp]);

  // A new session starts in the chat: its field takes the cursor, except on
  // a touch screen, where that would raise the keyboard over the page.
  useEffect(() => {
    const fine = window.matchMedia("(pointer: fine)").matches;
    if (defaultOpen && startsInChat.current && startsEmpty.current && fine) {
      setFocusSignal((n) => n + 1);
    }
    // Once, on the page's first render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A session started from the start view arrives with its first message
  // (lib/first-message): it goes out as this chat's first turn, through the
  // same queue as a message sent from the page. Before the paint, so the empty
  // chat's own start view is never seen first. Read into a ref, since a
  // development build runs this effect twice and the second pass would find
  // it already sent.
  // The message stays kept until the wizard has started on a turn (the panel
  // drops it then): a first turn that was refused is still there after a
  // reload, and goes back into the field. It is sent by its first reading only.
  useLayoutEffect(() => {
    if (handedOver.current !== undefined) return;
    const first = pendingFirstMessage(sessionId);
    handedOver.current = first;
    if (!first) return;
    // Only into a conversation that has not begun: a session that already has
    // messages, or a reply on its way, is not what the message was written for.
    if (initialMessages.length > 0 || pendingTurn) {
      dropFirstMessage(sessionId);
      return;
    }
    if (first.sentBefore) {
      // This page was loaded again after the turn was refused: the user's
      // words are in the field, as they were under the warning, to send again.
      setChatInput((current) => (current.trim() ? current : withoutStartLines(first.text)));
      return;
    }
    queuedCount.current += 1;
    setQueue([{ id: queuedCount.current, text: first.text, restoreOnFail: true }]);
    // The start view's field becomes this chat's field: it starts from where
    // that one stood (chat-panel). The page's own rise as it opens would hide
    // the field for its first frames, so it gives way to that one movement.
    if (typeof first.fieldTop === "number") {
      asideRef.current
        ?.closest("[data-session-content]")
        ?.getAnimations()
        .forEach((animation) => animation.cancel());
      setArrivedFrom(first.fieldTop);
    }
    // Once, as the session's page mounts.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The panel only exists while the dock is open; a message to send needs it.
  // A gate's approval also ends a change request that was being written about
  // that gate: its chip goes, so the next message is not sent as one. A chip
  // about another gate, or about anything else, stays.
  useEffect(() => {
    if (!autoSend) return;
    setOpen(true);
    const approved = approvedGateIn(autoSend);
    const key = approved ? `gate:${GATE_STEPS[approved - 1]}` : null;
    setReference((current) => (key && current?.key === key ? null : current));
  }, [autoSend]);

  // A message from the page still waiting to go out (an answer to what Gate 1 lacks, sent
  // while the wizard was answering) needs the panel too: collapsing the chat
  // meanwhile would leave it unsent until the chat was opened again.
  const waiting = queue.length > 0;
  useEffect(() => {
    if (waiting && !open) setOpen(true);
  }, [waiting, open]);

  // The dock opens when the session comes to wait on a gate while the page is
  // open (the default is read once, on load). It never closes by itself.
  const wasDefaultOpen = useRef(defaultOpen);
  useEffect(() => {
    const before = wasDefaultOpen.current;
    wasDefaultOpen.current = defaultOpen;
    if (defaultOpen && !before && window.matchMedia("(min-width: 1280px)").matches) setOpen(true);
  }, [defaultOpen]);

  useEffect(() => {
    const openChat = () => {
      setOpen(true);
      setFocusSignal((n) => n + 1);
    };
    // "Ask about this" from anywhere on the page: the chat opens with the item
    // as a chip and the cursor in the field. A new item replaces the chip.
    const askFromPage = (e: Event) => {
      const next = asChatReference((e as CustomEvent<unknown>).detail);
      if (!next) return;
      setReference(next);
      // Its draft goes into an empty field, or in place of the last draft left
      // untouched; words the user has typed are theirs and stay.
      const draft = next.draft;
      if (draft) {
        const previous = lastDraft.current;
        lastDraft.current = draft;
        setChatInput((current) => (!current.trim() || current === previous ? draft : current));
      }
      setOpen(true);
      setFocusSignal((n) => n + 1);
    };
    // A message the page sends as it is (an answer to what Gate 1 lacks): it goes
    // out as a chat turn of its own, without passing through the field.
    const sendFromPage = (e: Event) => {
      const text = (e as CustomEvent<string>).detail;
      if (typeof text !== "string" || !text.trim()) return;
      setOpen(true);
      queuedCount.current += 1;
      const queuedId = queuedCount.current;
      setQueue((q) => [...q, { id: queuedId, text }]);
    };
    window.addEventListener(OPEN_CHAT_EVENT, openChat);
    window.addEventListener(CHAT_REFERENCE_EVENT, askFromPage);
    window.addEventListener(CHAT_SEND_EVENT, sendFromPage);
    // "Muuta ratkaisua chatissa" on the case page (lib/case-chat): the page
    // kept its reference and came here, and the chat opens with it as it does
    // for a reference from this page. It is taken once.
    // In a ref, since a development build runs this effect twice: the
    // second pass found nothing to take, and below 1280 px the effect above had
    // closed the chat again by then.
    if (keptReference.current === undefined) keptReference.current = takeChatReference(sessionId);
    const kept = keptReference.current;
    if (kept) askFromPage(new CustomEvent<ChatReference>(CHAT_REFERENCE_EVENT, { detail: kept }));
    return () => {
      window.removeEventListener(OPEN_CHAT_EVENT, openChat);
      window.removeEventListener(CHAT_REFERENCE_EVENT, askFromPage);
      window.removeEventListener(CHAT_SEND_EVENT, sendFromPage);
    };
  }, [sessionId]);

  const saveWidth = (w: number) => {
    preferredWidth.current = w;
    userWidth.current = true;
    try {
      window.localStorage.setItem(WIDTH_KEY, String(w));
    } catch {
      // Not remembered; nothing else depends on it.
    }
  };

  function startDrag(e: React.PointerEvent<HTMLDivElement>) {
    if (e.button !== 0) return;
    e.preventDefault();
    const handle = e.currentTarget;
    const startX = e.clientX;
    const startWidth = width;
    let last = startWidth;
    handle.setPointerCapture(e.pointerId);
    setDragging(true);
    const previousSelect = document.body.style.userSelect;
    document.body.style.userSelect = "none";
    const move = (ev: PointerEvent) => {
      last = clamp(startWidth + (startX - ev.clientX));
      setWidth(last);
    };
    const end = () => {
      if (endDragRef.current !== end) return;
      endDragRef.current = null;
      setDragging(false);
      document.body.style.userSelect = previousSelect;
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", end);
      handle.removeEventListener("pointercancel", end);
      handle.removeEventListener("lostpointercapture", end);
      saveWidth(last);
    };
    endDragRef.current = end;
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", end);
    handle.addEventListener("pointercancel", end);
    handle.addEventListener("lostpointercapture", end);
  }

  function onHandleKey(e: React.KeyboardEvent<HTMLDivElement>) {
    const next =
      e.key === "ArrowLeft"
        ? width + KEY_STEP
        : e.key === "ArrowRight"
          ? width - KEY_STEP
          : e.key === "Home"
            ? MIN_WIDTH
            : e.key === "End"
              ? MAX_WIDTH
              : null;
    if (next === null) return;
    e.preventDefault();
    const w = clamp(next);
    setWidth(w);
    saveWidth(w);
  }

  // A double-click gives the width back to the step: its default now, and the
  // next step's default after it.
  function resetWidth() {
    const w = wide ? WIDE_WIDTH : DEFAULT_WIDTH;
    preferredWidth.current = w;
    userWidth.current = false;
    setWidth(clamp(w));
    try {
      window.localStorage.removeItem(WIDTH_KEY);
    } catch {
      // Nothing was remembered.
    }
  }

  return (
    <>
      {/* One element for both layouts, so the conversation keeps its state
          when the workspace appears beside it: the page's main content while
          the chat leads, a complementary panel once it docks. */}
      <div
        ref={asideRef}
        role={lead ? "main" : "complementary"}
        id={lead ? "main-content" : undefined}
        aria-label={chatTitle}
        data-testid="chat-dock"
        data-chat-open={open || lead ? "true" : "false"}
        data-chat-lead={lead ? "true" : undefined}
        style={{ "--chat-w": `${width}px` } as CSSProperties}
        className={
          lead
            ? "relative flex min-h-0 min-w-0 flex-1 flex-col"
            : `chat-bg relative flex min-h-0 shrink-0 flex-col border-l border-border ${
                open
                  ? "max-xl:fixed max-xl:z-30 max-xl:shadow-lg xl:w-[var(--chat-w)] md:max-xl:bottom-0 md:max-xl:right-0 md:max-xl:top-12 md:max-xl:w-[26rem] max-md:sheet-in max-md:inset-x-0 max-md:bottom-0 max-md:h-[60dvh] max-md:rounded-t-2xl max-md:border-l-0 max-md:border-t"
                  : "w-11 max-xl:hidden"
              } ${dragging ? "" : "transition-[width] duration-200 ease-out motion-reduce:transition-none"}`
        }
      >
        {lead && leadHeader}
        {open && !lead && (
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label={resizeLabel}
            aria-controls={panelId}
            aria-valuemin={MIN_WIDTH}
            aria-valuemax={maxWidth}
            aria-valuenow={width}
            tabIndex={0}
            title={resizeLabel}
            onPointerDown={startDrag}
            onKeyDown={onHandleKey}
            onDoubleClick={resetWidth}
            data-testid="chat-resize"
            className="group absolute inset-y-0 -left-1.5 z-10 hidden w-3 cursor-col-resize touch-none outline-none xl:block"
          >
            <span
              className={`absolute inset-y-0 left-1/2 w-0.5 -translate-x-1/2 transition-colors ${
                dragging ? "bg-brand" : "bg-transparent group-hover:bg-brand/60 group-focus-visible:bg-brand"
              }`}
            />
          </div>
        )}

        {(lead || open || replying) && (
          <ChatPanel
            id={panelId}
            sessionId={sessionId}
            initialMessages={initialMessages}
            chatTitle={chatTitle}
            greeting={greeting}
            aiNotice={aiNotice}
            assistantLabel={assistantLabel}
            inputPlaceholder={inputPlaceholder}
            inputLabel={inputLabel}
            sendLabel={sendLabel}
            streamFailedLabel={streamFailedLabel}
            thinkingLabel={thinkingLabel}
            startingLabel={startingLabel}
            wizardLive={wizardLive}
            inputValue={chatInput}
            onInputChange={setChatInput}
            autoSend={autoSend}
            busyLabel={busyLabel}
            errorLabels={errorLabels}
            questionLabels={questionLabels}
            activityLabels={activityLabels}
            hideChatLabel={hideChatLabel}
            onCollapse={() => {
              focusRailOnClose.current = true;
              setOpen(false);
            }}
            focusSignal={focusSignal}
            reference={reference}
            onReferenceChange={setReference}
            hidden={!open && !lead}
            lead={lead}
            onReplyingChange={setReplying}
            queue={queue}
            onQueuedTaken={(id) => setQueue((q) => q.filter((m) => m.id !== id))}
            pendingTurn={pendingTurn}
            gateAction={gateAction}
            arrivedFrom={arrivedFrom}
          />
        )}
        {!open && !lead && (
          <div className="flex h-full flex-col items-center gap-2 py-2.5">
            {/* The AI notice stays with the folded chat (AI Act art. 50): the
                description of the button that opens it, and in its tooltip. */}
            <p id={`${panelId}-rail-notice`} className="sr-only" data-testid="chat-rail-ai-notice">
              {aiNotice}
            </p>
            <button
              ref={railToggleRef}
              type="button"
              data-testid="chat-dock-toggle"
              onClick={() => {
                setOpen(true);
                setFocusSignal((n) => n + 1);
              }}
              aria-expanded={false}
              aria-controls={panelId}
              aria-label={showChatLabel}
              aria-describedby={`${panelId}-rail-notice`}
              title={`${showChatLabel}. ${aiNotice}`}
              className="icon-btn"
            >
              <Icon name="panelRightOpen" size={18} />
            </button>
            <button
              type="button"
              tabIndex={-1}
              aria-hidden
              onClick={() => setOpen(true)}
              title={aiNotice}
              className="rounded-md px-1 py-2 text-xs font-medium text-text-muted [writing-mode:vertical-rl] hover:text-text"
            >
              {chatTitle}
            </button>
          </div>
        )}
      </div>
    </>
  );
}

/**
 * Opens the chat and puts the cursor in the message field. Below the desktop
 * layout this is how the closed chat is reached; the first step uses it as its
 * start button.
 */
export function OpenChatButton({
  label,
  className,
  icon = true,
}: {
  label: string;
  className: string;
  icon?: boolean;
}) {
  return (
    <button
      type="button"
      data-open-chat
      onClick={() => window.dispatchEvent(new Event(OPEN_CHAT_EVENT))}
      className={className}
    >
      {icon && <Icon name="messageSquare" size={16} />}
      {label}
    </button>
  );
}
