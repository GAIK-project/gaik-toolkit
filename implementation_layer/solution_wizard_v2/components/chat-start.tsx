"use client";

import { useEffect, useId, useMemo, useRef, useState, useSyncExternalStore } from "react";
import type { ChatPanelLabels } from "@/lib/chat-activity";
import {
  DEFAULT_PACE,
  onBackgroundChange,
  onPaceChange,
  saveBackground,
  savePace,
  savedBackground,
  savedPace,
  type Background,
  type Pace,
} from "@/lib/chat-background";
import { exampleIn, examplesOffered, toggleExample } from "@/lib/session-start";
import { Icon, type IconName } from "./icons";

/**
 * The helpers of a first message: who the user is, how much the wizard asks,
 * and examples to start from. The start view (before a session exists) and an
 * empty session's chat show the same controls, driven by the same hook, so
 * both starts behave alike.
 */

// A chip that puts words into a field and shows whether they are there.
export function chipClass(on: boolean): string {
  // Taller under a finger than under a mouse pointer.
  return `inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-medium transition-[background-color,border-color,color,transform] duration-150 ease-out active:scale-[0.97] pointer-coarse:py-2 ${
    on
      ? "border-brand-soft-border bg-brand-soft text-brand-text"
      : "border-border-strong text-text-secondary hover:border-brand hover:text-brand-text"
  }`;
}

/** When a choice's label gives way to its icon: the width of the tools row it
 *  stands in (components/composer-card), where the two choices and the send
 *  button share one line. The longer label goes first. */
type Compact = "narrow" | "narrowest";
const LABEL_HIDDEN: Record<Compact, string> = {
  narrow: "@max-[12rem]:sr-only",
  narrowest: "@max-[17rem]:sr-only",
};

type ChoiceOption<T extends string> = { value: T; label: string; hint: string; icon: IconName };

/** The menu's width in px (w-72); narrower where the card is. */
const MENU_WIDTH = 288;

// One choice in the tools row of the message field, the way chat tools offer
// theirs: a pill that names what is chosen and opens a short menu, each option
// with a line on what it changes. The choice is state only: nothing is written
// into the field.
function ChoiceMenu<T extends string>({
  name,
  testId,
  options,
  chosen,
  onChoose,
  compact,
}: {
  /** What is being chosen: the menu's name, and the pill's words while nothing is chosen. */
  name: string;
  testId: string;
  options: readonly ChoiceOption<T>[];
  chosen: T | null;
  onChoose: (value: T) => void;
  compact: Compact;
}) {
  const [open, setOpen] = useState(false);
  // Where the menu starts in the card: under its pill, or as far left of it as
  // keeps the menu inside the card.
  const [left, setLeft] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  function show() {
    const pill = trigger.current;
    const card = pill?.offsetParent;
    if (pill && card) {
      const width = Math.min(MENU_WIDTH, card.clientWidth);
      setLeft(Math.max(0, Math.min(pill.offsetLeft, card.clientWidth - width)));
    }
    setOpen(true);
  }
  const current = options.find((option) => option.value === chosen) ?? null;

  const items = () => Array.from(box.current?.querySelectorAll<HTMLElement>('[role="menuitemradio"]') ?? []);

  // A press anywhere else puts the menu away. So does a window that changes
  // size: the menu was placed for the card as it was.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (e.target instanceof Node && !box.current?.contains(e.target)) setOpen(false);
    };
    const onResize = () => setOpen(false);
    document.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("resize", onResize);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("resize", onResize);
    };
  }, [open]);

  // The menu opens with the cursor on what is chosen.
  useEffect(() => {
    if (!open) return;
    const all = items();
    (all.find((el) => el.getAttribute("aria-checked") === "true") ?? all[0])?.focus();
  }, [open]);

  return (
    // The pills share the row's width: a long label is cut short before a
    // pill reaches the send button.
    <div ref={box} className="min-w-0" data-testid={testId}>
      <button
        ref={trigger}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        // The pill shows the choice; its name says what the choice is about.
        aria-label={current ? `${name}: ${current.label}` : name}
        title={current ? `${name}: ${current.label}` : name}
        onClick={() => (open ? setOpen(false) : show())}
        onKeyDown={(e) => {
          if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
          e.preventDefault();
          show();
        }}
        className={`inline-flex max-w-full items-center gap-1.5 rounded-full border border-border-strong px-2.5 py-1 text-xs font-medium transition-[background-color,border-color,color,transform] duration-150 ease-out hover:border-brand hover:text-brand-text active:scale-[0.97] pointer-coarse:py-1.5 ${
          open ? "border-brand bg-brand-soft text-brand-text" : current ? "text-text" : "text-text-secondary"
        }`}
      >
        <Icon name={current?.icon ?? options[0].icon} size={14} className="shrink-0" />
        <span className={`min-w-0 truncate ${LABEL_HIDDEN[compact]}`}>{current?.label ?? name}</span>
        <Icon
          name="chevronDown"
          size={13}
          className={`-mr-0.5 shrink-0 opacity-70 transition-transform duration-150 ease-out motion-reduce:transition-none ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>
      {open && (
        <div
          id={menuId}
          role="menu"
          aria-label={name}
          // Over the card, on the start view too: the AI notice is the line
          // under the card and stays in view while a choice is made.
          style={{ left }}
          className="pop-in absolute bottom-full z-40 mb-2 w-72 max-w-full rounded-xl border border-border bg-surface p-1 shadow-lg"
          onKeyDown={(e) => {
            const all = items();
            const at = all.indexOf(document.activeElement as HTMLElement);
            if (e.key === "Escape") {
              // This Esc is the menu's: the chat it stands in stays open.
              e.preventDefault();
              e.stopPropagation();
              setOpen(false);
              trigger.current?.focus();
            } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
              e.preventDefault();
              const step = e.key === "ArrowDown" ? 1 : -1;
              all[(Math.max(at, 0) + step + all.length) % all.length]?.focus();
            } else if (e.key === "Home" || e.key === "End") {
              e.preventDefault();
              all[e.key === "Home" ? 0 : all.length - 1]?.focus();
            } else if (e.key === "Tab") {
              setOpen(false);
            }
          }}
        >
          <p className="px-2.5 pb-1 pt-1.5 text-[11px] font-medium text-text-muted" aria-hidden>
            {name}
          </p>
          {options.map((option) => {
            const on = chosen === option.value;
            return (
              <button
                key={option.value}
                type="button"
                role="menuitemradio"
                aria-checked={on}
                onClick={() => {
                  setOpen(false);
                  onChoose(option.value);
                }}
                className="flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-surface-muted focus:bg-surface-muted focus:outline-none"
              >
                <Icon
                  name={option.icon}
                  size={16}
                  className={`mt-0.5 shrink-0 ${on ? "text-brand-text" : "text-text-muted"}`}
                />
                <span className="min-w-0 flex-1">
                  <span className={`block text-sm font-medium ${on ? "text-brand-text" : "text-text"}`}>
                    {option.label}
                  </span>
                  <span className="block text-xs leading-snug text-text-secondary">{option.hint}</span>
                </span>
                {on && <Icon name="check" size={16} className="mt-0.5 shrink-0 text-brand-text" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// Before the first message: who is the user? The wizard is told with the
// first message (lib/chat-background). Choosing the chosen one again takes
// the choice back.
export function BackgroundChoice({
  labels,
  chosen,
  onChoose,
}: {
  labels: ChatPanelLabels;
  chosen: Background | null;
  onChoose: (background: Background) => void;
}) {
  const options = useMemo(
    () =>
      [
        { value: "nonTechnical", label: labels.nonTechnical, hint: labels.nonTechnicalHint, icon: "user" },
        { value: "technical", label: labels.technical, hint: labels.technicalHint, icon: "codeXml" },
      ] as const,
    [labels.nonTechnical, labels.nonTechnicalHint, labels.technical, labels.technicalHint],
  );
  return (
    <ChoiceMenu
      name={labels.background}
      testId="chat-background"
      options={options}
      chosen={chosen}
      onChoose={onChoose}
      // The longer of the two labels: the first to give way to its icon.
      compact="narrowest"
    />
  );
}

// Before the first message: how much does the wizard ask? One of the two is
// always chosen; the wizard is told with the first message, as it is told who
// the user is.
export function PaceChoice({
  labels,
  chosen,
  onChoose,
}: {
  labels: ChatPanelLabels;
  chosen: Pace;
  onChoose: (pace: Pace) => void;
}) {
  const options = useMemo(
    () =>
      [
        { value: "quick", label: labels.quick, hint: labels.quickHint, icon: "zap" },
        { value: "thorough", label: labels.thorough, hint: labels.thoroughHint, icon: "listChecks" },
      ] as const,
    [labels.quick, labels.quickHint, labels.thorough, labels.thoroughHint],
  );
  return (
    <ChoiceMenu
      name={labels.pace}
      testId="chat-pace"
      options={options}
      chosen={chosen}
      onChoose={onChoose}
      compact="narrow"
    />
  );
}

const EXAMPLE_ICONS = ["fileHeadphone", "fileText", "messageSquareText", "fileSpreadsheet"] as const;

// The start view's examples: a chip puts a first message into the field, for
// the user to edit and send. They are there to start an empty field, so they
// step back once the user writes words of their own, and keep their place in
// the layout meanwhile: nothing moves under the cursor.
export function ExampleChips({
  labels,
  chosen,
  offered,
  onChoose,
}: {
  labels: ChatPanelLabels["start"];
  chosen: number | null;
  offered: boolean;
  onChoose: (index: number) => void;
}) {
  return (
    <div
      role="group"
      aria-label={labels.examples}
      data-testid="chat-examples"
      className={`flex flex-wrap items-center justify-center gap-x-2 gap-y-1.5 transition-[opacity,visibility] duration-150 ease-out motion-reduce:transition-none ${
        offered ? "" : "invisible opacity-0"
      }`}
    >
      {/* Before the chips on a wide window; on its own line above them on a phone. */}
      <span aria-hidden className="basis-full text-center text-xs text-text-muted sm:basis-auto">
        {labels.examples}
      </span>
      {labels.exampleList.map((example, i) => {
        const on = chosen === i;
        return (
          <button
            key={example.title}
            type="button"
            aria-pressed={on}
            title={example.prompt}
            onClick={() => onChoose(i)}
            className={chipClass(on)}
          >
            <Icon name={on ? "check" : (EXAMPLE_ICONS[i] ?? "fileText")} size={12} />
            {example.title}
          </button>
        );
      })}
    </div>
  );
}

/**
 * The choices and the examples of a first message. The choices are kept apart
 * from the field's text and remembered in this browser (lib/chat-background);
 * the chosen example is the text the field holds, so editing it unpresses its
 * chip. `focus` puts the cursor back into the field after a press.
 */
export function useStartChips(
  input: string,
  setInput: (value: string) => void,
  panel: ChatPanelLabels | undefined,
  focus: () => void,
) {
  const prompts = useMemo(
    () => (panel ? panel.start.exampleList.map((example) => example.prompt) : []),
    [panel],
  );
  // Read once the page is in the browser: the server does not know the choices.
  const background = useSyncExternalStore(onBackgroundChange, savedBackground, () => null);
  const pace = useSyncExternalStore(onPaceChange, savedPace, () => DEFAULT_PACE);

  function chooseBackground(chosen: Background) {
    saveBackground(background === chosen ? null : chosen);
    focus();
  }

  function choosePace(chosen: Pace) {
    savePace(chosen);
    focus();
  }

  function chooseExample(index: number) {
    if (!panel) return;
    setInput(toggleExample(input, prompts[index], prompts));
    focus();
  }

  return {
    background: panel ? background : null,
    chooseBackground,
    pace,
    choosePace,
    example: panel ? exampleIn(input, prompts) : null,
    examplesShown: panel ? examplesOffered(input, prompts) : false,
    chooseExample,
  };
}

/**
 * The lines that tell the wizard the choices, in the interface's language and
 * in the order they are sent: who the user is, then how much to ask. The
 * choices are read as they stand now unless they are given.
 */
export function startLines(
  panel: ChatPanelLabels | undefined,
  chosen: { background: Background | null; pace: Pace } = {
    background: savedBackground(),
    pace: savedPace(),
  },
): string[] {
  if (!panel) return [];
  const lines: string[] = [];
  if (chosen.background) {
    lines.push(chosen.background === "technical" ? panel.technicalText : panel.nonTechnicalText);
  }
  lines.push(chosen.pace === "thorough" ? panel.thoroughText : panel.quickText);
  return lines;
}
