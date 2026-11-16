"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  useTransition,
} from "react";
import { useRouter } from "next/navigation";
import type { ChatMessage, ChatRole, PendingTurn } from "@/lib/mock-sessions";
import {
  activityText,
  addStep,
  elapsedText,
  liveSteps,
  parseActivity,
  stepLine,
  type ChatActivityLabels,
  type TurnStep,
} from "@/lib/chat-activity";
import { START_LINES_ROOM, withStartLines, withoutStartLines } from "@/lib/chat-background";
import { MAX_CHAT_MESSAGE_CHARS, chatRefusalLabel, type ChatErrorLabels } from "@/lib/chat-limits";
import { dropFirstMessage } from "@/lib/first-message";
import {
  CHAT_REPLYING_EVENT,
  CHAT_SEND_DELIVERED_EVENT,
  CHAT_SEND_EVENT,
  CHAT_SEND_FAILED_EVENT,
  type ChatReference,
  type QueuedMessage,
} from "@/lib/chat-events";
import { setLocale } from "@/app/locale-actions";
import { approve } from "@/app/(app)/sessions/[id]/actions";
import { withoutStepParams } from "@/lib/step-redirect";
import { approvedGateIn, referenceMessage } from "@/lib/chat-reference";
import { STARTING_AFTER_MS, startingLineDelay } from "@/lib/wizard-start";
import { questionsIn } from "@/lib/chat-questions";
import { GATE_STEPS } from "@/lib/wizard-state-machine";
import { GLIDE_EASING, mayAnimate } from "@/lib/motion";
import { ChatMarkdown } from "./chat-markdown";
import { ChatQuestions, type ChatQuestionLabels } from "./chat-questions";
import { BackgroundChoice, ExampleChips, PaceChoice, startLines, useStartChips } from "./chat-start";
import { ComposerCard } from "./composer-card";
import { FileMention } from "./file-icon";
import { Icon } from "./icons";
import { PendingSubmitButton } from "./pending-submit-button";
import { ShowGateButton } from "./show-gate-button";

// No avatars: they took a column of the narrow chat and said nothing the
// layout does not. The user's messages sit right in a bubble; the wizard's
// answers read as text across the full width.
function MessageRow({
  role,
  assistantLabel,
  markdown = false,
  children,
}: {
  role: ChatRole;
  /** Read out before an assistant message, so a screen reader says who is speaking. */
  assistantLabel: string;
  markdown?: boolean;
  children: React.ReactNode;
}) {
  const isUser = role === "user";
  return (
    <div
      data-testid="chat-message"
      data-role={role}
      className={isUser ? "flex justify-end pl-8" : "pr-2"}
    >
      <div
        className={`text-sm leading-relaxed [overflow-wrap:anywhere] ${markdown ? "chat-md" : "whitespace-pre-wrap"} ${
          isUser
            ? "max-w-full rounded-2xl rounded-br-md bg-brand-soft px-3.5 py-2 text-text"
            : "text-text-secondary"
        }`}
      >
        {!isUser && <span className="sr-only">{assistantLabel}: </span>}
        {children}
      </div>
    </div>
  );
}

// While a reply is on its way (the real agent can take minutes on a turn):
// the step the wizard is on now as shimmering text, and under it the last two
// it finished in this reply, in the words the folded list uses afterwards. A
// step that has run for more than ten seconds shows how long, so a long check
// is seen to be running rather than stuck. The lines are updated in place:
// nothing here comes in with a movement.
function ThinkingStatus({
  label,
  steps,
  since,
  labels,
}: {
  /** Shown until the agent's first step. */
  label: string;
  steps: TurnStep[];
  /** When the running step started (or the turn, before the first), in ms. */
  since: number;
  labels?: ChatActivityLabels;
}) {
  const { current, finished } = liveSteps(steps);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const elapsed = labels && since > 0 ? elapsedText((now - since) / 1000, labels) : null;
  return (
    <div className="space-y-1 py-0.5" data-testid="chat-thinking">
      {/* The turning mark is seen at a glance; the words say what is being done. */}
      <span className="flex items-center gap-1.5 text-text-muted">
        <Icon name="loaderCircle" size={13} className="shrink-0 animate-spin motion-reduce:animate-none" />
        <span
          role="status"
          className="shimmer-text block min-w-0 truncate text-xs font-medium"
          data-testid="chat-activity"
        >
          {current ?? label}
        </span>
        {/* Not read out: the log is a live region, and a second counting up
            would be announced every time it changes. */}
        {elapsed && (
          <span aria-hidden className="shrink-0 text-xs tabular-nums" data-testid="chat-activity-elapsed">
            {elapsed}
          </span>
        )}
      </span>
      {finished.length > 0 && (
        <ul className="m-0 list-none space-y-0.5 p-0 text-xs text-text-muted" data-testid="chat-activity-finished">
          {finished.map((step) => (
            // Keyed by its place in the turn: a step keeps its line as newer ones finish.
            <li key={step.at} className="m-0 flex items-center gap-1.5 p-0">
              <Icon name="check" size={12} className="shrink-0" />
              <span className="min-w-0 truncate">{step.text}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// After the reply, the steps of that turn stay under it, folded away.
function WorkSteps({ summary, steps }: { summary: string; steps: string[] }) {
  return (
    <details className="group mt-2 text-xs text-text-muted" data-testid="chat-steps">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded hover:text-text">
        <Icon name="chevronRight" size={12} className="transition-transform group-open:rotate-90" />
        {summary}
      </summary>
      <ol className="mt-1 space-y-0.5 border-l border-border pl-3">
        {steps.map((step, i) => (
          <li key={i} className="[overflow-wrap:anywhere]">
            {/* A step that names a file shows the file type's mark before it. */}
            <FileMention text={step} />
          </li>
        ))}
      </ol>
    </details>
  );
}

// Something that happened rather than something said: the wake-up turn a gate
// approval in the panel sends to the agent. The user did not write it, so it
// is not shown as their bubble.
function EventLine({ children }: { children: React.ReactNode }) {
  return (
    <div
      data-testid="chat-event"
      className="flex items-center gap-3 text-xs text-text-muted before:h-px before:flex-1 before:bg-border after:h-px after:flex-1 after:bg-border"
    >
      <span className="inline-flex items-center gap-1.5">
        <Icon name="circleCheck" size={14} className="text-success-text" />
        {children}
      </span>
    </div>
  );
}

function newMessageId(): string {
  if (typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `msg_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 9)}`;
}

const NO_QUEUE: QueuedMessage[] = [];

// The steps of finished turns, by session, reply text and which reply with
// that text it is (two replies that read the same keep their own steps). They
// live outside the panel so that closing the chat (which unmounts it) or the
// server's copy of the messages (with new ids) does not lose them; a page
// reload clears them, and only the newest MAX_FINISHED_STEPS replies are kept.
const MAX_FINISHED_STEPS = 200;
const finishedSteps = new Map<string, string[]>();

/** Each assistant reply's key in `finishedSteps`, by message id. */
function stepsKeys(sessionId: string, messages: ChatMessage[]): Map<string, string> {
  const seen = new Map<string, number>();
  const keys = new Map<string, string>();
  for (const m of messages) {
    if (m.role !== "assistant" || !m.content) continue;
    const nth = seen.get(m.content) ?? 0;
    seen.set(m.content, nth + 1);
    keys.set(m.id, `${sessionId}\n${nth}\n${m.content}`);
  }
  return keys;
}

function rememberSteps(key: string, steps: string[]) {
  finishedSteps.delete(key); // written again, it is the newest
  finishedSteps.set(key, steps);
  for (const oldest of finishedSteps.keys()) {
    if (finishedSteps.size <= MAX_FINISHED_STEPS) break;
    finishedSteps.delete(oldest);
  }
}

/** The gate a reference chip is about ("gate:9" is gate 2), or null for any other chip. */
function gateOf(reference: ChatReference | null): number | null {
  const step = reference?.key.match(/^gate:(\d+)$/);
  const at = step ? GATE_STEPS.indexOf(Number(step[1])) : -1;
  return at < 0 ? null : at + 1;
}

/** The stream itself said the turn failed: nothing to read again. */
class ReplyFailed extends Error {}

/**
 * The gate decision the session waits for. The wizard's reply at a gate ends
 * by asking for the approval, so the newest reply carries the approve button:
 * the same action, in the same words, as the bar under the workspace.
 */
export type ChatGateAction = {
  gateStep: number;
  /** The gate's decision ("Hyväksy testiajo") and what the button says meanwhile. */
  label: string;
  pendingLabel: string;
  /** The page shows a notice from a refused action; the approval clears it. */
  hadNotice?: boolean;
  /** "Show me": points at the gate's decision bar on the page; `name` is its accessible name. */
  show?: { label: string; name: string };
};

export function ChatPanel({
  id,
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
  inputValue,
  onInputChange,
  autoSend,
  busyLabel,
  activityLabels,
  errorLabels,
  questionLabels,
  hideChatLabel,
  onCollapse,
  focusSignal = 0,
  reference = null,
  onReferenceChange,
  hidden = false,
  lead = false,
  onReplyingChange,
  queue = NO_QUEUE,
  onQueuedTaken,
  pendingTurn = null,
  gateAction,
  arrivedFrom = null,
}: {
  id: string;
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
  inputValue: string;
  onInputChange: (value: string) => void;
  autoSend?: string;
  busyLabel: string;
  activityLabels?: ChatActivityLabels;
  errorLabels?: ChatErrorLabels;
  /** Labels for answering a round of questions one by one. */
  questionLabels?: ChatQuestionLabels;
  /** Label of the button in the header that collapses the chat to its rail. */
  hideChatLabel: string;
  onCollapse: () => void;
  /** Bumped by the dock to move focus into the message field. */
  focusSignal?: number;
  /** The item on the page the next message is about, shown as a chip above the field. */
  reference?: ChatReference | null;
  /** Null removes the chip: the user removed it, or the message about it was sent. */
  onReferenceChange?: (reference: ChatReference | null) => void;
  /** The chat was closed while a reply is arriving: the panel stays, out of
   *  sight, so the reply is there when the chat is opened again. */
  hidden?: boolean;
  /** The chat is the page (lib/session-start): one column on the page's middle
   *  line, without the dock's title bar, and an empty one opens as a start view. */
  lead?: boolean;
  /** Tells the dock whether a reply is arriving. */
  onReplyingChange?: (replying: boolean) => void;
  /** Messages the page sends as they are (CHAT_SEND_EVENT), oldest first. */
  queue?: QueuedMessage[];
  /** Called as a message is taken off the queue to be sent. */
  onQueuedTaken?: (id: number) => void;
  /** The message the wizard is answering although this panel did not send it:
   *  the page was reloaded mid-reply, or another tab sent it. */
  pendingTurn?: PendingTurn | null;
  gateAction?: ChatGateAction;
  /** The session was started by a first message on the start view: where that
   *  view's field stood, in px from the window's top (lib/first-message). */
  arrivedFrom?: number | null;
}) {
  const panel = activityLabels?.panel;
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  // The start view: the chat is the page and nothing has been said in it yet.
  // A page loaded in the middle of the first reply already has a conversation.
  // Nor is it shown under a message that is about to go out: the first one,
  // handed over by the start view that created the session.
  const start =
    lead && messages.length === 0 && queue.length === 0 && !pendingTurn && panel ? panel.start : null;
  const [streaming, setStreamingState] = useState(false);
  // Also in a ref: an effect that fires on new page data must know whether a
  // reply is on screen now, not when the effect was created.
  const streamingRef = useRef(false);
  const setStreaming = useCallback((value: boolean) => {
    streamingRef.current = value;
    setStreamingState(value);
  }, []);
  useEffect(() => {
    onReplyingChange?.(streaming);
    window.dispatchEvent(new CustomEvent<boolean>(CHAT_REPLYING_EVENT, { detail: streaming }));
  }, [streaming, onReplyingChange]);
  // The message sent is waiting for a wizard that is being started: the
  // waiting line says so until the answer opens (lib/wizard-start). Whether
  // one is held is what the page read, and true once a message was answered.
  const [starting, setStarting] = useState(false);
  const liveRef = useRef(wizardLive);
  useEffect(() => {
    liveRef.current = wizardLive;
  }, [wizardLive]);
  const waitingLabel = starting && startingLabel ? startingLabel : thinkingLabel;
  // Asked for the other language, the wizard offers the switch as a button
  // under its reply (the reply language follows the interface language, which
  // only the user can set). Pressing it switches the interface and tells the
  // wizard to go on in that language.
  const [languageOffer, setLanguageOffer] = useState<{
    replyId: string;
    locale: "fi" | "en";
  } | null>(null);
  const [switchingLanguage, startLanguageSwitch] = useTransition();
  function switchLanguage(locale: "fi" | "en") {
    const offer = panel?.languageOffer[locale];
    if (!offer) return;
    startLanguageSwitch(async () => {
      const data = new FormData();
      data.set("locale", locale);
      try {
        await setLocale(data);
      } catch {
        // The switch did not go through: the button stays, to press again.
        return;
      }
      setLanguageOffer(null);
      // The button is gone with the offer; the field is where the user goes on.
      focusInput();
      window.dispatchEvent(new CustomEvent(CHAT_SEND_EVENT, { detail: offer.message }));
    });
  }
  // A typed message was refused because the wizard is answering another one:
  // said above the field until the next send.
  const [busyNote, setBusyNote] = useState(false);
  // The reply whose answer form is sending: the form stays under it, with its
  // answers, until the agent has started on them.
  const [answeringId, setAnsweringId] = useState<string | null>(null);
  // The steps the agent has taken in the running turn (from its tool activity),
  // and those of finished turns, kept for this page view.
  const [turnSteps, setTurnStepsState] = useState<TurnStep[]>([]);
  const turnStepsRef = useRef<TurnStep[]>([]);
  // When the running step started, or the turn before its first step.
  const [stepSince, setStepSince] = useState(0);
  const setTurnSteps = useCallback((steps: TurnStep[]) => {
    turnStepsRef.current = steps;
    setTurnStepsState(steps);
    setStepSince(Date.now());
  }, []);
  const [stepsByMessage, setStepsByMessage] = useState<Record<string, string[]>>({});
  const keysOfSteps = useMemo(() => stepsKeys(sessionId, messages), [sessionId, messages]);
  useEffect(() => {
    for (const m of messages) {
      const steps = stepsByMessage[m.id];
      const key = keysOfSteps.get(m.id);
      if (steps && key) rememberSteps(key, steps);
    }
  }, [messages, stepsByMessage, keysOfSteps]);
  const stepsOf = (m: ChatMessage) => {
    const key = keysOfSteps.get(m.id);
    return stepsByMessage[m.id] ?? (key ? finishedSteps.get(key) : undefined);
  };
  // The messages the user sent from this panel, by id. One of them is never
  // shown as a gate approval, whatever it says.
  const typedIds = useRef(new Set<string>());
  // The replies that arrived in this page view and have not shown their
  // answer form yet: the form comes in once, under such a reply only.
  const freshReplies = useRef(new Set<string>());
  const listRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const inputId = `${id}-input`;
  const router = useRouter();

  // Follow the conversation while the reader is at its end; someone who has
  // scrolled up to re-read an answer is left where they are until they send.
  const followRef = useRef(true);
  // The messages inside the log: its height is what grows as a reply arrives.
  const contentRef = useRef<HTMLDivElement>(null);
  // Where the log last put itself, and where it stood at the last scroll: a
  // scroll event at the first is the panel's own, and the second tells which
  // way the reader moved.
  const ownTop = useRef(-1);
  const lastTop = useRef(0);
  // The answer form already brought into view (the element itself).
  const shownForm = useRef<Element | null>(null);
  // Puts a following reader at the end of the conversation. With an answer
  // form under the newest reply that is taller than the log, the form's top
  // goes to the top of the log instead, once: its first field is where the
  // reader goes on, and the end would have hidden it. Only the log scrolls;
  // the page stays where it is.
  const settle = useCallback(() => {
    const log = listRef.current;
    // A closed chat has no height to scroll in; it settles when it is opened.
    if (!log || !followRef.current || log.clientHeight === 0) return;
    const end = Math.max(0, log.scrollHeight - log.clientHeight);
    const form =
      contentRef.current?.lastElementChild?.querySelector('[data-testid="chat-questions"]') ?? null;
    let top = end;
    if (form) {
      const formTop = form.getBoundingClientRect().top - log.getBoundingClientRect().top + log.scrollTop;
      const firstField = Math.max(0, formTop - 12);
      if (firstField < end) {
        // Shown already: the reader is in the form, and it stays under them.
        if (shownForm.current === form) return;
        top = firstField;
      }
    }
    shownForm.current = form;
    if (Math.abs(log.scrollTop - top) < 1) return;
    log.scrollTo({ top, behavior: "instant" });
    ownTop.current = log.scrollTop;
  }, []);
  useEffect(() => {
    if (!hidden) settle();
  }, [messages, hidden, settle]);
  // The log's content grows without a new message too: the answer form and
  // the steps come in when a reply ends, a diagram is drawn after its text,
  // and the field under the log takes room from it as it grows or a notice
  // appears above it. Each used to leave the end of the conversation below
  // the fold.
  useEffect(() => {
    const log = listRef.current;
    const content = contentRef.current;
    if (!log || !content || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(settle);
    observer.observe(log);
    observer.observe(content);
    return () => observer.disconnect();
  }, [settle]);

  // Into the field, after what is already there (a draft, a background sentence).
  const focusInput = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  }, []);
  useEffect(() => {
    if (focusSignal > 0) focusInput();
  }, [focusSignal, focusInput]);

  // The wizard has had a message from the user, sent here or elsewhere. The
  // first one says who they are and how much to ask (lib/chat-background); one
  // that never reached the wizard leaves that still to say.
  const heardInSession = initialMessages.some((m) => m.role === "user");
  const userHeard = useRef(Boolean(pendingTurn) || heardInSession);
  // The same, for what is drawn: the field keeps room for the lines the next
  // message will carry for as long as it will carry them. (It kept the room
  // only while the chat was empty: a first message the wizard refused is in
  // the chat, its resend still gets the lines, and near the length limit that
  // resend was refused for being too long.)
  const [heardHere, setHeardHere] = useState(Boolean(pendingTurn));
  const startLinesAhead = !heardHere && !heardInSession;

  // Messages appended on the server arrive as new props after revalidation. This state was seeded once, so without adopting
  // them the chat showed nothing until a manual reload: the "no visible
  // feedback" half of #126. Only grow from the server list, so an optimistic
  // message added by `send()` (not yet persisted) is never dropped, and never
  // mid-stream.
  useEffect(() => {
    if (initialMessages.some((m) => m.role === "user")) userHeard.current = true;
    if (streaming) return;
    setMessages((current) =>
      initialMessages.length > current.length ? initialMessages : current,
    );
  }, [initialMessages, streaming]);

  // The start view became this conversation: its field is this field. It
  // starts from where that one stood and settles under the conversation, while
  // the first message comes into view above it. Once, before the first paint,
  // and after the field has taken its height (components/composer-card).
  const formRef = useRef<HTMLFormElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const landed = useRef(false);
  useLayoutEffect(() => {
    if (arrivedFrom === null || landed.current) return;
    landed.current = true;
    const form = formRef.current;
    const box = boxRef.current;
    if (!box || !mayAnimate(form)) return;
    const shift = arrivedFrom - box.getBoundingClientRect().top;
    if (Math.abs(shift) < 1) return;
    form.animate([{ transform: `translateY(${shift}px)` }, { transform: "none" }], {
      duration: 320,
      easing: GLIDE_EASING,
    });
    listRef.current?.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 240, easing: "ease-out" });
  }, [arrivedFrom]);

  // A gate approved in the panel reaches the agent as one chat turn (#173). The
  // page passes it as `autoSend` from the URL the approve action redirected to;
  // it is sent once and the URL is cleaned so a reload does not send it again.
  const autoSent = useRef<string | null>(null);
  useEffect(() => {
    if (!autoSend) {
      // The address has lost its wake-up: the next approval's is a new one,
      // also when it reads the same (the same gate, reopened for a change and
      // approved again on this page). It was taken for the one already sent,
      // and the wizard never heard of the second approval.
      autoSent.current = null;
      return;
    }
    if (streaming || autoSent.current === autoSend) return;
    autoSent.current = autoSend;
    // Only the wake-up leaves the address; the open tab stays in it.
    router.replace(withoutStepParams(window.location.pathname, window.location.search));
    void sendText(autoSend, { retryWhileBusy: true, keepInput: true, typed: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSend, streaming]);

  // What is in the field and above it now, for a send that fails after the
  // user has gone on writing.
  const latestInput = useRef(inputValue);
  latestInput.current = inputValue;
  const latestReference = useRef(reference);
  latestReference.current = reference;

  // Messages from the page (an answer to what Gate 1 lacks) go out one at a time,
  // each once a running reply has finished, like typed ones. The dock drops a
  // message as it is taken, so closing and reopening the chat does not send it
  // again. A wizard still busy with another turn (a gate's wake-up, say) is
  // waited for, as the wake-up itself waits.
  const takenId = useRef<number | null>(null);
  // The last typed message was refused because the wizard was answering another.
  const busyRefused = useRef(false);
  useEffect(() => {
    const next = queue[0];
    if (!next || streaming || takenId.current === next.id) return;
    takenId.current = next.id;
    onQueuedTaken?.(next.id);
    void sendText(
      next.text,
      next.restoreOnFail
        ? // The user's own first message: refused or failed, it is back in
          // the field at once, under the warning that says why. Only their
          // words: the choices' lines are not text in the field.
          { fromPage: true, onFailed: () => onInputChange(withoutStartLines(next.text)) }
        : { retryWhileBusy: true, fromPage: true },
    );
    // sendText reads only refs, props and setters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queue, streaming]);

  async function send(e?: React.FormEvent<HTMLFormElement>) {
    e?.preventDefault();
    if (streaming) return;
    if (reference) {
      // The message about a chip starts with its line. A chip alone sends nothing.
      const message = referenceMessage(reference.prefix, inputValue);
      if (!message) return;
      const about = reference;
      const typed = inputValue;
      onReferenceChange?.(null);
      // An answer that never reached the agent (the wizard was busy, the
      // message was refused) comes back with its chip, to send again. What
      // the user wrote or picked in the meantime stays as it is.
      if (!(await sendText(message, { first: true }))) {
        const wroteMore = latestInput.current.trim() !== "";
        if (!wroteMore && !latestReference.current) onReferenceChange?.(about);
        if (!wroteMore) onInputChange(typed);
      }
      return;
    }
    const typed = inputValue;
    if (!(await sendText(typed, { first: true })) && busyRefused.current && !latestInput.current.trim()) {
      // Refused because another reply is on its way: the words come back.
      onInputChange(typed);
    }
  }

  // The helpers of a first message: who the user is, how much the wizard
  // asks, and examples to start from (chat-start). After a press the field takes the focus at once, so
  // words typed straight after it go after an example; the cursor is put at
  // its end once it is drawn.
  const { background, chooseBackground, pace, choosePace, example, examplesShown, chooseExample } = useStartChips(
    inputValue,
    onInputChange,
    panel,
    () => {
      textareaRef.current?.focus();
      requestAnimationFrame(focusInput);
    },
  );

  // Resolves true once the agent has started on the message, false when it
  // never reached it (empty, already busy here, refused or failed to start).
  async function sendText(
    raw: string,
    {
      retryWhileBusy = false,
      fromPage = false,
      first = false,
      keepInput,
      typed = true,
      onStarted,
      onFailed,
    }: {
      retryWhileBusy?: boolean;
      fromPage?: boolean;
      /** Written in this chat's field: the user's first such message tells
       *  the wizard who they are and how much to ask (lib/chat-background). */
      first?: boolean;
      /** Leave what the user is typing in the field (a page message, a gate's wake-up). */
      keepInput?: boolean;
      /** False for the wake-up turn the page sends after a gate approval. */
      typed?: boolean;
      /** The agent has started on the message. */
      onStarted?: () => void;
      /** The message never reached the agent; `reason` is what the chat says. */
      onFailed?: (reason: string) => void;
    } = {},
  ): Promise<boolean> {
    const said = raw.trim();
    if (!said || streaming) return false;
    // What the user chose (who they are, how much to ask) goes ahead of their
    // first message, as it is sent: the field never held it, and the message
    // is shown without it.
    const text = first && !userHeard.current ? withStartLines(said, startLines(panel)) : said;

    const ts = new Date().toISOString();
    const userId = newMessageId();
    const asstId = newMessageId();
    if (typed) typedIds.current.add(userId);
    // A message from the page that never reached the agent goes back to its
    // sender (CHAT_SEND_FAILED_EVENT), so it is not lost.
    let started = false;
    const notDelivered = (reason: string) => {
      // Under the words the sender gave: it knows its message by them.
      if (fromPage) window.dispatchEvent(new CustomEvent(CHAT_SEND_FAILED_EVENT, { detail: said }));
      onFailed?.(reason);
    };

    // A message from the page (an answer to what Gate 1 lacks, the answers to a
    // round of questions) leaves what the user is typing where it is.
    if (!(keepInput ?? fromPage)) onInputChange("");
    busyRefused.current = false;
    setBusyNote(false);
    // An offer under an earlier reply is not this turn's.
    setLanguageOffer(null);
    followRef.current = true;
    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", content: text, createdAt: ts },
      { id: asstId, role: "assistant", content: "", createdAt: ts },
    ]);
    setTurnSteps([]);
    setStreaming(true);

    // wizard_api answers once the wizard is up: at once when one is held,
    // and after its start when not, which is when the line says so.
    // An answer that only says to wait (the loop below) ends the line: the
    // wizard is busy or has no free slot, which is not a start. The line comes
    // back if the answer to a later try is late in its turn.
    let toldToWait = false;
    const post = async () => {
      const delay = toldToWait ? STARTING_AFTER_MS : startingLineDelay(liveRef.current);
      if (delay === 0) setStarting(true);
      const late = delay === 0 ? undefined : window.setTimeout(() => setStarting(true), delay);
      try {
        return await fetch(`/api/sessions/${sessionId}/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text }),
        });
      } finally {
        window.clearTimeout(late);
      }
    };

    try {
      let res = await post();
      // 409: the agent is still answering the previous message; 503: no agent
      // slot is free; 429: the user's own agents are all busy, or they are over
      // the per-minute message limit. The gate wake-up waits (up to a minute)
      // so the approval is not lost; a message the user typed is told to wait.
      const waitable = (status: number) => status === 409 || status === 503 || status === 429;
      for (let attempt = 0; waitable(res.status) && retryWhileBusy && attempt < 12; attempt++) {
        toldToWait = true;
        // A wizard that is answering another message is up.
        if (res.status === 409) liveRef.current = true;
        setStarting(false);
        await new Promise((r) => setTimeout(r, 5000));
        res = await post();
      }
      if (res.status === 409) {
        if (typed && !fromPage && !retryWhileBusy) {
          // The wizard is answering a message sent elsewhere (another tab, or
          // before a reload). What the user wrote goes back into the field,
          // and the reply on its way is shown here once the page has read it.
          setMessages((prev) => prev.filter((m) => m.id !== userId && m.id !== asstId));
          busyRefused.current = true;
          setBusyNote(true);
          onFailed?.(busyLabel);
          return false;
        }
        setMessages((prev) =>
          prev.map((m) => (m.id === asstId ? { ...m, content: `⚠︎ ${busyLabel}` } : m)),
        );
        notDelivered(busyLabel);
        return false;
      }
      const refusalCode =
        res.status === 429 ? ((await res.json().catch(() => ({}))) as { error?: unknown }).error : undefined;
      const refusal = chatRefusalLabel(res.status, refusalCode, errorLabels);
      if (refusal) {
        setMessages((prev) =>
          prev.map((m) => (m.id === asstId ? { ...m, content: `⚠︎ ${refusal}` } : m)),
        );
        notDelivered(refusal);
        return false;
      }
      if (!res.ok || !res.body) throw new Error("stream failed");
      started = true;
      // The wizard is up and on the message.
      liveRef.current = true;
      setStarting(false);
      userHeard.current = true;
      setHeardHere(true);
      // The wizard has a turn of this session: the start view's message, kept
      // until now for a reload after a refusal, has nothing left to hand over.
      dropFirstMessage(sessionId);
      if (fromPage) window.dispatchEvent(new CustomEvent(CHAT_SEND_DELIVERED_EVENT, { detail: said }));
      onStarted?.();

      let whole = false;
      try {
        whole = await readReply(res.body, asstId);
      } catch (err) {
        if (err instanceof ReplyFailed) throw err;
      }
      // The connection broke, or was closed on the way, while the wizard goes
      // on answering: the reply is read again from the turn that is running.
      if (!whole && !(await rejoinReply(userId, asstId))) throw new Error("stream lost");
    } catch {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === asstId && !m.content
            ? { ...m, content: `⚠︎ ${streamFailedLabel}` }
            : m,
        ),
      );
      if (!started) notDelivered(streamFailedLabel);
    } finally {
      setStarting(false);
      turnEnded(asstId);
    }
    return started;
  }

  // The reply this panel sent for lost its connection: a network that changed,
  // a proxy that closed a long response. The turn goes on at the server, and
  // the next message would be refused as "still finishing" until a reload.
  // Reads the running turn from its start into the same message, as a
  // reloaded page does. False when it cannot be reached.
  async function rejoinReply(userId: string, asstId: string): Promise<boolean> {
    for (let attempt = 0; attempt < 4; attempt++) {
      await new Promise((r) => setTimeout(r, 1500 * (attempt + 1)));
      try {
        const res = await fetch(`/api/sessions/${sessionId}/chat/stream`, { cache: "no-store" });
        if (res.status === 204) {
          // It ended in the meantime: the stored conversation has the whole
          // exchange, and the page reads it as the turn ends.
          setMessages((prev) => prev.filter((m) => m.id !== userId && m.id !== asstId));
          return true;
        }
        if (res.status !== 200 || !res.body) continue;
        setMessages((prev) => prev.map((m) => (m.id === asstId ? { ...m, content: "" } : m)));
        setTurnSteps([]);
        if (await readReply(res.body, asstId)) return true;
      } catch (err) {
        if (err instanceof ReplyFailed) throw err;
        // Still no connection: try again.
      }
    }
    return false;
  }

  // Reads one reply's frames into the assistant message `asstId`, until the
  // stream closes (the exchange is stored by then). Throws ReplyFailed when
  // the stream reports a failure, and whatever the connection throws when it
  // breaks. True when the stream said how the turn ended (its last frame, or a
  // limit it told about); false when it just stopped.
  async function readReply(body: ReadableStream<Uint8Array>, asstId: string): Promise<boolean> {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let ended = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const line = frame.startsWith("data: ") ? frame.slice(6) : frame;
        if (!line.trim()) continue;
        const evt = JSON.parse(line);
        if (evt.done || evt.error) ended = true;
        if (evt.error && evt.limit === "turns" && errorLabels) {
          // Not a failure: what the agent did so far stands, and it goes on
          // when the user sends another message.
          const note = `⚠︎ ${errorLabels.turnLimit}`;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === asstId ? { ...m, content: m.content ? `${m.content}\n\n${note}` : note } : m,
            ),
          );
          continue;
        }
        if (evt.error && evt.code === "agent_busy" && errorLabels) {
          // The agent had to be restarted mid-turn and the user's own
          // agents were all busy: the same message as a 429 agent_busy.
          const note = `⚠︎ ${errorLabels.agentBusy}`;
          setMessages((prev) => prev.map((m) => (m.id === asstId ? { ...m, content: note } : m)));
          continue;
        }
        if (evt.error) throw new ReplyFailed();
        // The agent changed the session itself (it reopened a gate): the page
        // shows that now, not when the reply is whole.
        if (evt.session_changed) router.refresh();
        if (evt.offer_locale === "fi" || evt.offer_locale === "en") {
          setLanguageOffer({ replyId: asstId, locale: evt.offer_locale });
        }
        const act = parseActivity(evt);
        if (act && activityLabels) {
          // Each frame is a tool starting: the step before it is finished,
          // and the same step again is counted on its line.
          setTurnSteps(addStep(turnStepsRef.current, activityText(act, activityLabels)));
        }
        if (evt.narration_end) {
          // What streamed so far was the agent narrating a tool call, or an
          // internal notice; the reply comes after it (#168).
          setMessages((prev) =>
            prev.map((m) => (m.id === asstId ? { ...m, content: "" } : m)),
          );
        }
        if (evt.delta) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === asstId ? { ...m, content: m.content + evt.delta } : m,
            ),
          );
        }
      }
    }
    return ended;
  }

  // A reply is whole (or has failed): its steps fold away under it and the
  // page reads the session again, so the step, the gates and the tabs show
  // what this exchange changed.
  function turnEnded(asstId: string) {
    freshReplies.current.add(asstId);
    setStreaming(false);
    const steps = turnStepsRef.current.map(stepLine);
    if (steps.length) setStepsByMessage((prev) => ({ ...prev, [asstId]: steps }));
    setTurnSteps([]);
    router.refresh();
  }

  // The wizard is answering a message this panel did not send: the page was
  // reloaded mid-reply (the reply used to be lost, and the next message was
  // refused as "still finishing"), or another tab sent it. The message and
  // the reply so far are shown, and the rest arrives as it would have.
  async function joinTurn(userMessage: string) {
    const ts = new Date().toISOString();
    const userId = newMessageId();
    const asstId = newMessageId();
    followRef.current = true;
    // The reply the note spoke of is the one shown from here on.
    setBusyNote(false);
    setLanguageOffer(null);
    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", content: userMessage, createdAt: ts },
      { id: asstId, role: "assistant", content: "", createdAt: ts },
    ]);
    setTurnSteps([]);
    setStreaming(true);
    try {
      const res = await fetch(`/api/sessions/${sessionId}/chat/stream`, { cache: "no-store" });
      if (res.status !== 200 || !res.body) {
        // The reply was finished in the meantime: the stored conversation has
        // it, and the page reads it below.
        setMessages((prev) => prev.filter((m) => m.id !== userId && m.id !== asstId));
        return;
      }
      await readReply(res.body, asstId);
    } catch {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === asstId && !m.content ? { ...m, content: `⚠︎ ${streamFailedLabel}` } : m,
        ),
      );
    } finally {
      turnEnded(asstId);
    }
  }

  // Joined once per turn. A turn this panel is already showing (it sent the
  // message, and the page data was read again mid-reply) is not joined.
  const joinedTurn = useRef<string | null>(null);
  useEffect(() => {
    if (!pendingTurn || joinedTurn.current === pendingTurn.startedAt) return;
    joinedTurn.current = pendingTurn.startedAt;
    if (streamingRef.current) return;
    void joinTurn(pendingTurn.userMessage);
    // joinTurn reads only refs, props and setters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingTurn]);

  // Answers from the form under the reply `replyId`. The form stays there
  // while they are on their way. If they never reach the agent, their bubble
  // and the warning under it are taken back out, so the form is again under
  // the newest reply, with the answers in it, and says why they were not sent.
  async function sendAnswers(replyId: string, message: string): Promise<string | null> {
    const outcome: { failure: string | null } = { failure: null };
    setAnsweringId(replyId);
    const delivered = await sendText(message, {
      retryWhileBusy: true,
      fromPage: true,
      onStarted: () => setAnsweringId(null),
      onFailed: (reason) => {
        outcome.failure = reason;
      },
    });
    setAnsweringId(null);
    if (delivered) return null;
    // Nothing was added to the chat when the send did not get that far.
    if (outcome.failure === null) return streamFailedLabel;
    setMessages((prev) => {
      const at = prev.findIndex((m) => m.id === replyId);
      return at < 0 ? prev : prev.slice(0, at + 1);
    });
    return outcome.failure;
  }

  // Until the user has written anything, the chat greets them and asks who
  // they are; above a real conversation the greeting would only be noise.
  const empty = !messages.some((m) => m.role === "user");
  const referenceId = `${id}-reference`;
  const noticeId = `${id}-ai-notice`;
  // The gate the chip above the field is about, if it is about one.
  const gate = gateOf(reference);
  // While the chat is the page, the conversation and the field share one
  // column on the page's middle line.
  const column = lead ? "mx-auto w-full max-w-3xl" : "";

  return (
    <div
      id={id}
      className={`${hidden ? "hidden" : "flex"} min-h-0 flex-1 flex-col ${
        // The start view sits a little above the middle, as one group. In a
        // window too short for it (a phone on its side, the steps opened
        // above it) it starts at the top and scrolls instead of spilling out.
        start ? "scroll-thin justify-center-safe overflow-y-auto pb-[10dvh]" : ""
      }`}
    >
      {lead ? (
        start ? (
          <div className="shrink-0 px-4 pb-6 text-center" data-testid="chat-start">
            {/* The only heading here, at the size the start view gives the
                product's name; the logo is on the start view alone. */}
            <h2 className="text-2xl font-semibold leading-tight tracking-[-0.02em] text-text-strong sm:text-[1.875rem]">
              {start.title}
            </h2>
            <p className="mx-auto mt-2 max-w-prose text-balance text-sm leading-relaxed text-text-secondary">
              {start.lede}
            </p>
          </div>
        ) : (
          // The page header names the session; the chat needs no bar of its own.
          <h2 className="sr-only">{chatTitle}</h2>
        )
      ) : (
        <div className="flex min-h-11 shrink-0 items-center justify-between gap-2 border-b border-border py-1.5 pl-4 pr-2">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-text">{chatTitle}</h2>
            {/* Always in view: the replies come from an AI (AI Act art. 50(1)).
                Here rather than under the field, where it took a row from the
                conversation. */}
            <p id={noticeId} className="text-text-muted" data-testid="chat-ai-notice">
              {aiNotice}
            </p>
          </div>
          <button
            type="button"
            data-testid="chat-dock-toggle"
            onClick={onCollapse}
            aria-expanded
            aria-controls={id}
            aria-label={hideChatLabel}
            title={hideChatLabel}
            className="icon-btn"
          >
            <Icon name="panelRightClose" size={18} className="max-md:hidden" />
            <Icon name="chevronDown" size={18} className="md:hidden" />
          </button>
        </div>
      )}

      <div
        ref={listRef}
        role="log"
        aria-live="polite"
        aria-relevant="additions text"
        onScroll={(e) => {
          const el = e.currentTarget;
          const top = el.scrollTop;
          const wentUp = top < lastTop.current - 1;
          lastTop.current = top;
          // The panel's own move says nothing about the reader.
          if (Math.abs(top - ownTop.current) < 1) return;
          ownTop.current = -1;
          // A reader who moves up, however little, is reading: the reply
          // arriving below does not pull them back. Near the end again, they
          // follow it. (A log whose content shrank is still at its end.)
          const gap = el.scrollHeight - top - el.clientHeight;
          followRef.current = wentUp ? gap < 2 : gap < 48;
        }}
        // Nothing to show in the start view: the log takes no room there.
        className={`scroll-thin relative overflow-auto ${start ? "shrink-0" : "flex-1 px-4 py-4"}`}
      >
        <div ref={contentRef} className={`space-y-4 ${column}`}>
        {empty && !start && (
          <div data-testid="chat-empty">
            <MessageRow role="assistant" assistantLabel={assistantLabel}>
              {greeting}
            </MessageRow>
          </div>
        )}

        {messages.map((m, i) => {
          const isAsst = m.role === "assistant";
          const approvedGate =
            !isAsst && panel && !typedIds.current.has(m.id) ? approvedGateIn(m.content) : null;
          if (approvedGate !== null && panel) {
            return <EventLine key={m.id}>{panel.gateApproved.replace("{n}", String(approvedGate))}</EventLine>;
          }
          // Answer fields only under the newest reply, once it has finished,
          // and under the reply being answered while its answers are sent.
          const asking = answeringId ? m.id === answeringId : !streaming && i === messages.length - 1;
          const questions = questionLabels && isAsst && asking ? questionsIn(m.content) : [];
          // The reply being streamed. While the agent works after a remark
          // ("Let me check the spreadsheet"), its text is already on screen,
          // so the progress line goes under it instead of replacing the dots.
          const inProgress = streaming && isAsst && i === messages.length - 1;
          // The user's own words: the lines their first message was sent
          // with are not part of them (lib/chat-background).
          const shown = isAsst ? m.content : withoutStartLines(m.content) || m.content;
          return (
            <MessageRow
              key={m.id}
              role={m.role}
              assistantLabel={assistantLabel}
              markdown={isAsst && !!m.content}
            >
              {shown ? (
                isAsst ? (
                  <>
                    <ChatMarkdown content={m.content} final={!inProgress} labels={activityLabels} />
                    {inProgress && turnSteps.length > 0 && (
                      <div className="mt-1.5">
                        <ThinkingStatus
                          label={waitingLabel}
                          steps={turnSteps}
                          since={stepSince}
                          labels={activityLabels}
                        />
                      </div>
                    )}
                    {!inProgress && activityLabels && stepsOf(m) && (
                      <WorkSteps
                        summary={activityLabels.steps.replace("{n}", String(stepsOf(m)!.length))}
                        steps={stepsOf(m)!}
                      />
                    )}
                    {languageOffer?.replyId === m.id && panel && (
                      <button
                        type="button"
                        disabled={switchingLanguage || streaming}
                        onClick={() => switchLanguage(languageOffer.locale)}
                        data-testid="chat-language-offer"
                        className="btn-secondary mt-2 px-3 py-1.5 text-xs"
                      >
                        {panel.languageOffer[languageOffer.locale].label}
                      </button>
                    )}
                    {questionLabels && questions.length >= 2 && (
                      <ChatQuestions
                        key={m.id}
                        questions={questions}
                        labels={questionLabels}
                        disabled={streaming}
                        onSend={(message) => sendAnswers(m.id, message)}
                        enter={freshReplies.current.has(m.id)}
                        onEntered={() => freshReplies.current.delete(m.id)}
                      />
                    )}
                    {/* The approval the reply asks for, where it is read. Not
                        under a reply that asks questions: those come first. */}
                    {gateAction && !streaming && i === messages.length - 1 && questions.length < 2 && (
                      <form
                        action={approve}
                        className="reveal-in mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1"
                        data-testid="chat-gate-action"
                      >
                        <input type="hidden" name="id" value={sessionId} />
                        <input type="hidden" name="step" value={gateAction.gateStep} />
                        {gateAction.hadNotice && <input type="hidden" name="notice" value="1" />}
                        <PendingSubmitButton
                          label={gateAction.label}
                          pendingLabel={gateAction.pendingLabel}
                          icon="check"
                          className="btn-secondary px-3 py-1.5 text-xs"
                        />
                        {gateAction.show && <ShowGateButton {...gateAction.show} />}
                      </form>
                    )}
                  </>
                ) : (
                  shown
                )
              ) : streaming ? (
                <ThinkingStatus
                  label={waitingLabel}
                  steps={turnSteps}
                  since={stepSince}
                  labels={activityLabels}
                />
              ) : null}
            </MessageRow>
          );
        })}
        </div>
      </div>

      <form
        ref={formRef}
        onSubmit={send}
        className={`shrink-0 px-3 pb-2 ${lead ? "sm:px-4" : "border-t border-border pt-3"}`}
      >
        <div className={column}>
        <label htmlFor={inputId} className="sr-only">
          {inputLabel}
        </label>
        {reference && (
          // Keyed by the item, so a new reference comes in as a new chip.
          <div
            key={reference.key}
            data-testid="chat-reference"
            className="chat-chip-in mb-2 flex w-fit max-w-full items-center gap-1.5 rounded-md border border-brand-soft-border bg-brand-soft py-0.5 pl-2 pr-0.5 text-xs text-brand-text"
          >
            <Icon name="messageSquareText" size={13} />
            <span id={referenceId} className="min-w-0 truncate" title={reference.label}>
              {reference.label}
            </span>
            <button
              type="button"
              onClick={() => {
                onReferenceChange?.(null);
                focusInput();
              }}
              aria-label={panel ? `${panel.referenceRemove}: ${reference.label}` : reference.label}
              title={panel?.referenceRemove}
              data-testid="chat-reference-remove"
              className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded text-brand-text transition-colors duration-150 hover:bg-brand/10"
            >
              <Icon name="x" size={13} />
            </button>
          </div>
        )}
        {busyNote && (
          <p role="status" data-testid="chat-busy-note" className="mb-2 px-1 text-xs text-warning-text">
            {busyLabel}
          </p>
        )}
        {/* One card holds the field and, under it, its tools and the send
            button, so nothing beside the field moves when it grows. */}
        <ComposerCard
          fieldRef={textareaRef}
          boxRef={boxRef}
          fieldId={inputId}
          value={inputValue}
          onChange={onInputChange}
          onEnter={() => void send()}
          // The chip's line goes in front of what is typed here.
          // And the choices' lines in front of the first message the wizard
          // takes: by the same word that adds them when it is sent (sendText).
          maxLength={Math.max(
            1,
            MAX_CHAT_MESSAGE_CHARS -
              (reference ? reference.prefix.length + 2 : 0) -
              (startLinesAhead ? START_LINES_ROOM : 0),
          )}
          // With a gate's chip above it, the field says what to write: the
          // change wanted at that gate, which goes to the wizard.
          placeholder={
            start
              ? start.placeholder
              : gate !== null && panel
                ? panel.gatePlaceholder.replace("{n}", String(gate))
                : inputPlaceholder
          }
          describedBy={reference ? `${referenceId} ${noticeId}` : noticeId}
          large={!!start}
          // Who the user is and how much to ask, until their first message
          // has said it. Not over a first message that is on its way from the
          // start view: the field lands as the one line it stays, with no row
          // that is gone a frame later.
          tools={
            empty && panel && queue.length === 0 ? (
              <>
                <BackgroundChoice labels={panel} chosen={background} onChoose={chooseBackground} />
                <PaceChoice labels={panel} chosen={pace} onChoose={choosePace} />
              </>
            ) : null
          }
          sendLabel={sendLabel}
          // The chat shows that the wizard is working; the button only dims.
          sendDisabled={streaming}
        />
        {/* Always in view: the replies come from an AI (AI Act art. 50(1)).
            The chat that is the page has no header to carry it. */}
        {lead && (
          <p
            id={noticeId}
            className={`mt-1.5 px-1 text-xs text-text-muted ${start ? "text-center" : ""}`}
            data-testid="chat-ai-notice"
          >
            {aiNotice}
          </p>
        )}
        {/* The start view's examples sit under the field they fill. */}
        {start && panel && (
          <div className="mt-4">
            <ExampleChips
              labels={start}
              chosen={example}
              offered={examplesShown}
              onChoose={chooseExample}
            />
          </div>
        )}
        </div>
      </form>
    </div>
  );
}
