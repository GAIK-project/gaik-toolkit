"use client";

import { useEffect, useId, useRef, useState, useTransition } from "react";
import { reopen } from "@/app/(app)/sessions/[id]/actions";
import type { GateStatus } from "@/lib/sessions";
import { askInChat } from "@/lib/chat-events";
import { fillTemplate } from "@/lib/chat-template";
import { gateReference } from "@/lib/gate-guide";
import { stageState as stageStateFor, type StageState } from "@/lib/gate-timeline-state";
import { Icon } from "./icons";

/** The timeline's copy that the rest of the shell shares (lib/i18n). */
export type TimelineGuide = {
  /** Each gate's business topic, Gate 1–4. */
  topics: string[];
  /** Each gate's decision, named on its row ("Hyväksy ratkaisun rakenne"). */
  decisions: string[];
  /** What the user checks when approving each gate. */
  checks: string[][];
  checksTitle: string;
  /** "Muuta", in an approved stage once it is opened, and its accessible name ({topic}). */
  change: string;
  changeLabel: string;
  /** The chat reference a change starts: chip ({n}, {topic}) and message prefix. */
  chip: string;
  changePrefix: string;
  /** Reopening an approved gate for a change: the question ({n}) and its buttons. */
  reopen: {
    question: string;
    confirm: string;
    cancel: string;
    working: string;
    busy: string;
    failed: string;
  };
};

type Props = {
  sessionId: string;
  locale: "fi" | "en";
  step: number;
  phases: string[];
  gateSteps: number[];
  gateStatus: Record<number, GateStatus>;
  phaseCount: number;
  guide: TimelineGuide;
  /** "row": the four gates across the session bar (md and up), each opening
   *  its stage under it; "inline": a card under the step line on a phone. */
  variant: "row" | "inline";
};

type Stage = {
  steps: { step: number; name: string }[];
  gateStep: number | null;
};

/** A pointer crossing the bar opens nothing: it has to rest on a stage this long. */
const HOVER_OPEN_MS = 120;
/** Room to move from a stage into its panel, or back, before the panel leaves. */
const HOVER_CLOSE_MS = 220;

const LABELS = {
  en: {
    title: "Steps",
    phaseOf: (a: number, b: number) => `Step ${a} / ${b}`,
    rejected: "Rejected",
    gatesDone: (done: number, all: number) => `${done} of ${all} gates approved`,
    allDone: "Done",
  },
  fi: {
    title: "Vaiheet",
    phaseOf: (a: number, b: number) => `Vaihe ${a} / ${b}`,
    rejected: "Hylätty",
    gatesDone: (done: number, all: number) => `${done}/${all} gatea hyväksytty`,
    allDone: "Valmis",
  },
} as const;

/**
 * The phases grouped by the gate that closes them, each stage one mark
 * (approved, in progress, ahead) with its business topic. That answers "where
 * am I, what comes next" at a glance. The rest is in the stage's panel: its
 * steps, what its approval checks (a press on the gate's row), and "Change"
 * for a stage that is approved. In the row a mouse resting on a stage opens the
 * panel, and it leaves with the pointer; a press keeps it until a press
 * elsewhere or Esc, which is also how a touch screen and the keyboard open it.
 * The panel lies over the page, so nothing moves while it is read.
 */
export function GateTimeline({
  sessionId,
  locale,
  step,
  phases,
  gateSteps,
  gateStatus,
  phaseCount,
  guide,
  variant,
}: Props) {
  const L = LABELS[locale];
  const inRow = variant === "row";
  const panelId = useId();
  const nav = useRef<HTMLElement>(null);

  // Group the phases: each stage ends at its gate.
  const stages: Stage[] = [];
  let cur: { step: number; name: string }[] = [];
  phases.forEach((name, i) => {
    const s = i + 1;
    if (gateSteps.includes(s)) {
      stages.push({ steps: cur, gateStep: s });
      cur = [];
    } else {
      cur.push({ step: s, name });
    }
  });
  if (cur.length) stages.push({ steps: cur, gateStep: null });

  const stageBounds = (st: Stage) => {
    const first = st.steps[0]?.step ?? st.gateStep ?? 0;
    const last = st.gateStep ?? st.steps[st.steps.length - 1]?.step ?? first;
    return { first, last };
  };
  const stageState = (st: Stage): StageState =>
    stageStateFor(step, stageBounds(st), st.gateStep, gateStatus);

  // The card on a phone. No override = auto: the current stage is open, the
  // others closed. A press on a stage overrides that for the stage.
  const [collapsed, setCollapsed] = useState<Record<number, boolean>>({});
  const autoCollapsed = (st: Stage) => stageState(st) !== "current";
  const toggle = (idx: number, st: Stage) =>
    setCollapsed((c) => ({ ...c, [idx]: !(c[idx] ?? autoCollapsed(st)) }));

  // "Change" on an approved gate asks first (below): the gate it asks about.
  const [asking, setAsking] = useState<number | null>(null);

  // The row: one stage's panel at a time, none until a stage is pressed. A
  // question asked in a panel leaves with it, so a panel opened again starts
  // from its steps, not from a question that takes the focus.
  const [openStage, setOpenStage] = useState<number | null>(null);
  // Pressed open (or pressed inside): the panel stays when the pointer leaves.
  const [pinned, setPinned] = useState(false);
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const clearHover = () => {
    if (hoverTimer.current) clearTimeout(hoverTimer.current);
    hoverTimer.current = null;
  };
  useEffect(() => clearHover, []);
  useEffect(() => {
    if (!inRow || openStage === null) return;
    // A press anywhere else on the page puts the panel away.
    const onPointerDown = (e: PointerEvent) => {
      if (!(e.target instanceof Node) || nav.current?.contains(e.target)) return;
      clearHover();
      setOpenStage(null);
      setPinned(false);
      setAsking(null);
    };
    // Esc puts the panel away and the focus back on its stage. Heard on the
    // document, so it also works when the control that had the focus has left
    // the panel; an Esc pressed elsewhere (the chat, a dialog) is not this one.
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      const target = e.target;
      if (!(target instanceof Node)) return;
      if (target !== document.body && !nav.current?.contains(target)) return;
      e.stopPropagation();
      nav.current
        ?.querySelector<HTMLElement>(`[data-testid="timeline-stage-${openStage}"]`)
        ?.focus();
      clearHover();
      setOpenStage(null);
      setPinned(false);
      setAsking(null);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [inRow, openStage]);

  // What a gate's approval checks, shown under its row on request.
  const [checksOpen, setChecksOpen] = useState<Record<number, boolean>>({});

  // "Change" on an approved gate asks first: reopening takes back that
  // approval and the later ones. Once reopened, the chat opens with the gate
  // as the reference, where the user says what to change.
  const [reopenError, setReopenError] = useState<string | null>(null);
  const [reopening, startReopen] = useTransition();
  // The gate was reopened meanwhile (by the wizard, or in another tab): the
  // question is answered, and must not come back open when it is approved again.
  const askedStep = asking === null ? undefined : gateSteps[asking - 1];
  const askedStillApproved = askedStep === undefined || gateStatus[askedStep] === "approved";
  useEffect(() => {
    if (!askedStillApproved) setAsking(null);
  }, [askedStillApproved]);
  const reopenGate = (gate: number, gateStep: number) =>
    startReopen(async () => {
      setReopenError(null);
      const outcome = await reopen(sessionId, gate).catch(() => "failed" as const);
      if (outcome === "busy") {
        setReopenError(guide.reopen.busy);
        return;
      }
      if (outcome === "failed") {
        setReopenError(guide.reopen.failed);
        return;
      }
      // "not_approved": another tab reopened it first; the page now shows it.
      setAsking(null);
      // The row's panel has done its job: the change is said in the chat.
      setOpenStage(null);
      setPinned(false);
      askInChat(
        gateReference(
          { topics: guide.topics, chip: guide.chip, prefix: guide.changePrefix },
          gate,
          gateStep,
        ),
      );
    });

  // How far the session is, in the unit the user decides in: approved gates.
  const approvedGates = gateSteps.filter((s) => gateStatus[s] === "approved").length;
  const allApproved = gateSteps.length > 0 && approvedGates === gateSteps.length;

  /** A stage's mark: a check once approved, its gate's number until then. */
  const stageMark = (state: StageState, gate: number) => (
    <span
      className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
        state === "approved"
          ? "bg-brand text-on-brand"
          : state === "current"
            ? "border-2 border-brand text-brand-text"
            : "border border-border-strong text-text-muted"
      }`}
      aria-hidden
    >
      {state === "approved" ? <Icon name="check" size={14} /> : gate}
    </span>
  );

  /**
   * What a press on a stage shows, in the row's panel and in the phone's
   * card alike: its steps, the gate that closes it with what its approval
   * checks, and "Change" once it is approved.
   */
  const stageBody = (st: Stage) => {
    const state = stageState(st);
    const gs = st.gateStep ? gateStatus[st.gateStep] : undefined;
    const gate = st.gateStep ? gateSteps.indexOf(st.gateStep) + 1 : 0;
    const topic = gate ? guide.topics[gate - 1] : "";
    const atGate = st.gateStep === step;
    const checks = gate ? (guide.checks[gate - 1] ?? []) : [];
    const showChecks = Boolean(checksOpen[gate]) && state !== "approved" && checks.length > 0;
    return (
      <>
        <ol className={`mb-1.5 border-l border-border pl-3 ${inRow ? "ml-[10px]" : "ml-[19px]"}`}>
          {st.steps.map((s) => {
            const isDone = s.step < step;
            const isCur = s.step === step;
            return (
              <li
                key={s.step}
                aria-current={isCur ? "step" : undefined}
                className="flex items-center gap-2 py-1 text-[13px]"
              >
                {isDone ? (
                  <Icon name="check" size={13} className="text-brand-strong" />
                ) : (
                  <span
                    className={`mx-[3.5px] h-1.5 w-1.5 shrink-0 rounded-full ${
                      isCur ? "bg-brand ring-4 ring-brand-soft" : "bg-border-strong"
                    }`}
                    aria-hidden
                  />
                )}
                <span
                  className={
                    isCur
                      ? "font-semibold text-brand-text"
                      : isDone
                        ? "text-text-secondary"
                        : "text-text-muted"
                  }
                >
                  {s.name}
                </span>
              </li>
            );
          })}
          {st.gateStep && (
            <li aria-current={atGate ? "step" : undefined} className="mt-0.5 text-[13px]">
              <div
                className={`flex items-center gap-2 rounded-md py-0.5 ${
                  atGate && state === "current" ? "-ml-1.5 bg-brand-soft pl-1.5" : ""
                }`}
              >
                <Icon
                  name={state === "approved" ? "circleCheck" : state === "current" ? "flag" : "circle"}
                  size={13}
                  className={
                    state === "approved" || (atGate && state === "current")
                      ? "text-brand-strong"
                      : "text-text-muted"
                  }
                />
                <span
                  className={`min-w-0 flex-1 ${
                    atGate && state === "current" ? "font-semibold text-brand-text" : "text-text-secondary"
                  }`}
                >
                  {gate ? guide.decisions[gate - 1] : ""}
                </span>
                {/* A rejected gate says so; the one being decided is marked by
                    its colour alone. The row says it beside the stage itself,
                    in view without a press, so its panel does not repeat it. */}
                {!inRow && state === "current" && atGate && gs === "rejected" && (
                  <span className="shrink-0 text-[11px] font-medium text-danger-text">{L.rejected}</span>
                )}
                {/* What the approval checks, behind its own control: the
                    row itself is named like the approve button, so it
                    is not one. */}
                {state !== "approved" && checks.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setChecksOpen((open) => ({ ...open, [gate]: !open[gate] }))}
                    aria-expanded={showChecks}
                    aria-label={`${guide.checksTitle} ${topic}`}
                    title={`${guide.checksTitle} ${topic}`}
                    data-testid={`gate-checks-toggle-${gate}`}
                    className={`icon-btn hit-area h-7 w-7 ${showChecks ? "bg-brand-soft text-brand-text" : ""}`}
                  >
                    <Icon name="listChecks" size={14} />
                  </button>
                )}
              </div>
              {showChecks && (
                <div className="reveal-in pb-1 pl-[21px] pt-1" data-testid={`gate-checks-${gate}`}>
                  <p className="text-[11px] font-medium text-text-muted">{guide.checksTitle}</p>
                  <ul className="mt-1 space-y-0.5 text-[12px] leading-snug text-text-secondary">
                    {checks.map((item) => (
                      <li key={item} className="flex gap-1.5">
                        <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-border-strong" aria-hidden />
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </li>
          )}
        </ol>

        {/* An approved stage can be asked to change in the chat: the
            agent owns the artifacts, so a change goes to it. */}
        {state === "approved" && gate > 0 && st.gateStep && asking !== gate && (
          <button
            type="button"
            onClick={() => {
              setReopenError(null);
              setAsking(gate);
            }}
            aria-label={fillTemplate(guide.changeLabel, { topic })}
            data-testid={`gate-change-${gate}`}
            className={`btn-inline mb-2 mt-0.5 ${inRow ? "ml-[22px]" : "ml-[31px]"}`}
          >
            <Icon name="pencil" size={12} />
            {guide.change}
          </button>
        )}
        {state === "approved" && gate > 0 && st.gateStep && asking === gate && (
          <div
            role="group"
            aria-label={fillTemplate(guide.changeLabel, { topic })}
            data-testid={`gate-reopen-${gate}`}
            className={`reveal-in mb-2 mr-2 border-t border-border pt-2 text-[12px] leading-snug text-text-secondary ${
              inRow ? "ml-[22px]" : "ml-[31px]"
            }`}
          >
            <p>{fillTemplate(guide.reopen.question, { n: String(gate) })}</p>
            {reopenError && (
              <p role="alert" className="mt-1 text-warning-text">
                {reopenError}
              </p>
            )}
            <div className="mt-2 flex flex-wrap gap-1.5">
              {/* "Change" left as the question came: the answer takes the focus. */}
              <button
                type="button"
                autoFocus
                disabled={reopening}
                onClick={() => reopenGate(gate, st.gateStep as number)}
                data-testid={`gate-reopen-confirm-${gate}`}
                className="btn-secondary px-2 py-1 text-[12px]"
              >
                {reopening ? guide.reopen.working : guide.reopen.confirm}
              </button>
              <button
                type="button"
                disabled={reopening}
                onClick={(e) => {
                  // Back to where the question was asked from.
                  const list = e.currentTarget.closest("nav");
                  setAsking(null);
                  requestAnimationFrame(() => {
                    list?.querySelector<HTMLElement>(`[data-testid="gate-change-${gate}"]`)?.focus();
                  });
                }}
                className="btn-ghost px-2 py-1 text-[12px]"
              >
                {guide.reopen.cancel}
              </button>
            </div>
          </div>
        )}
      </>
    );
  };

  if (!inRow) {
    // On a narrow screen the line under the phase title already says what to
    // do now, so the card is the list alone.
    return (
      // No taller than most of the screen: with every stage open the card
      // pushed the step's view out of a phone's window; the list scrolls inside.
      <nav
        aria-label={L.title}
        className="scroll-thin max-h-[60dvh] overflow-y-auto rounded-lg border border-border bg-surface px-1 py-1.5"
      >
        <ol className="space-y-0.5">
          {stages.map((st, idx) => {
            const state = stageState(st);
            const isCollapsed = collapsed[idx] ?? autoCollapsed(st);
            const gate = st.gateStep ? gateSteps.indexOf(st.gateStep) + 1 : 0;
            return (
              <li key={idx}>
                <button
                  type="button"
                  onClick={() => toggle(idx, st)}
                  aria-expanded={!isCollapsed}
                  data-testid={gate ? `timeline-stage-${gate}` : undefined}
                  data-state={state}
                  className="flex min-h-11 w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left transition-colors duration-150 hover:bg-surface-muted active:bg-border"
                >
                  {stageMark(state, gate)}
                  <span
                    className={`min-w-0 flex-1 truncate text-[13px] ${
                      state === "current"
                        ? "font-semibold text-text"
                        : state === "approved"
                          ? "font-medium text-text-secondary"
                          : "font-medium text-text-muted"
                    }`}
                  >
                    {gate ? guide.topics[gate - 1] : ""}
                  </span>
                  <Icon
                    name="chevronDown"
                    size={14}
                    className={`text-text-secondary transition-transform duration-150 motion-reduce:transition-none ${isCollapsed ? "-rotate-90" : ""}`}
                  />
                </button>
                {!isCollapsed && <div className="reveal-in">{stageBody(st)}</div>}
              </li>
            );
          })}
        </ol>
      </nav>
    );
  }

  return (
    <>
      <nav
        ref={nav}
        aria-label={L.title}
        // Below the widest layout a stage's panel is placed from the row's
        // own ends, so it never reaches past the window's edge. Where every
        // stage has its name, a long session name gives way, not the row.
        className="relative hidden min-w-0 md:block xl:shrink-0"
      >
        {/* The list's name says how far the session is, in approved gates. */}
        <ol
          aria-label={L.gatesDone(approvedGates, gateSteps.length)}
          data-testid="gate-ring"
          className="flex items-center"
        >
          {stages.map((st, idx) => {
            const gate = st.gateStep ? gateSteps.indexOf(st.gateStep) + 1 : 0;
            // Every phase belongs to a gate's stage; one without would have no mark.
            if (!gate) return null;
            const state = stageState(st);
            const open = openStage === gate;
            const before = stages[idx - 1];
            const rejected =
              state === "current" && st.gateStep === step && gateStatus[st.gateStep] === "rejected";
            return (
              <li
                key={gate}
                className="flex items-center xl:relative"
                // A mouse only: a finger's press is the click below.
                onPointerEnter={(e) => {
                  if (e.pointerType !== "mouse") return;
                  clearHover();
                  if (open || (pinned && openStage !== null)) return;
                  const show = () => {
                    setOpenStage(gate);
                    setPinned(false);
                    setAsking(null);
                  };
                  // From one open stage to the next the panel follows at once.
                  if (openStage !== null) show();
                  else hoverTimer.current = setTimeout(show, HOVER_OPEN_MS);
                }}
                onPointerLeave={(e) => {
                  if (e.pointerType !== "mouse") return;
                  clearHover();
                  if (pinned) return;
                  hoverTimer.current = setTimeout(
                    () => setOpenStage((now) => (now === gate ? null : now)),
                    HOVER_CLOSE_MS,
                  );
                }}
              >
                {before && (
                  <span
                    aria-hidden
                    className={`h-px w-3 shrink-0 xl:w-4 ${
                      stageState(before) === "approved" ? "bg-brand" : "bg-border-strong"
                    }`}
                  />
                )}
                <button
                  type="button"
                  onClick={() => {
                    clearHover();
                    // A press on a panel the pointer opened keeps it.
                    const close = open && pinned;
                    setOpenStage(close ? null : gate);
                    setPinned(!close);
                    setAsking(null);
                  }}
                  aria-expanded={open}
                  aria-controls={`${panelId}-${gate}`}
                  data-testid={`timeline-stage-${gate}`}
                  data-state={state}
                  // A menu button: its ground fills under the pointer and while
                  // its panel is open, and the chevron darkens with it.
                  className={`group/stage flex min-h-9 items-center gap-2 rounded-lg px-1.5 py-1.5 transition-colors duration-150 hover:bg-surface-muted active:bg-border pointer-coarse:min-h-11 ${
                    open ? "bg-surface-muted" : ""
                  }`}
                >
                  {stageMark(state, gate)}
                  {/* Where the bar is narrow, only the stage in progress keeps
                      its name in view; the others are their marks. */}
                  <span
                    className={`whitespace-nowrap text-sm ${
                      state === "current"
                        ? "font-semibold text-text"
                        : `max-xl:sr-only font-medium ${
                            state === "approved" ? "text-text-secondary" : "text-text-muted"
                          }`
                    }`}
                  >
                    {guide.topics[gate - 1]}
                  </span>
                  {/* Says that the stage opens, and turns while it is open; beside a name only. */}
                  <Icon
                    name="chevronDown"
                    size={14}
                    className={`-ml-0.5 transition-[color,transform] duration-150 group-hover/stage:text-text motion-reduce:transition-none ${
                      open ? "rotate-180 text-text" : "text-text-secondary"
                    } ${state === "current" ? "" : "max-xl:hidden"}`}
                  />
                </button>
                {rejected && (
                  <span className="ml-0.5 mr-1 shrink-0 text-[11px] font-medium text-danger-text">
                    {L.rejected}
                  </span>
                )}
                {open && (
                  // The panel sits clear of the bar's lower edge, which the row
                  // is a little above; the gap belongs to this box, so a pointer
                  // on its way from the stage to the panel never leaves them.
                  <div
                    className={`absolute top-full z-30 w-[21rem] max-w-[calc(100vw-2rem)] pt-3 ${gate <= 2 ? "left-0" : "right-0"}`}
                    onPointerDown={() => setPinned(true)}
                    onFocus={() => setPinned(true)}
                  >
                    <div
                      id={`${panelId}-${gate}`}
                      className="pop-in rounded-lg border border-border bg-surface p-2.5 shadow-lg"
                    >
                      {/* Where the bar shows this stage as its mark alone, the panel names it. */}
                      {state !== "current" && (
                        <p className="mb-1.5 px-1 text-[13px] font-semibold text-text xl:hidden" aria-hidden>
                          {guide.topics[gate - 1]}
                        </p>
                      )}
                      {stageBody(st)}
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      </nav>
      {/* The four stages show where the session is, so the step count is not
          drawn; it stays for a screen reader (a phone has it in its own step
          line). The bar's end says only that the session is done. */}
      <p
        data-testid="timeline-progress"
        className={
          allApproved
            ? "ml-auto hidden shrink-0 text-xs text-text-muted xl:block"
            : "sr-only max-md:hidden"
        }
      >
        {allApproved ? L.allDone : L.phaseOf(step, phaseCount)}
      </p>
    </>
  );
}
