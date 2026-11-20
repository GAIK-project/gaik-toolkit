"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { startSessionFromMessage } from "@/app/actions";
import {
  BackgroundChoice,
  ExampleChips,
  PaceChoice,
  startLines,
  useStartChips,
} from "@/components/chat-start";
import { ComposerCard } from "@/components/composer-card";
import type { ChatPanelLabels } from "@/lib/chat-activity";
import { START_LINES_ROOM, withStartLines } from "@/lib/chat-background";
import { MAX_CHAT_MESSAGE_CHARS } from "@/lib/chat-limits";
import { keepFirstMessage } from "@/lib/first-message";
import { FOCUS_START_EVENT } from "@/lib/shell";

export type StartViewLabels = {
  /** The chat's own words: the question, the lede, the chips. */
  panel: ChatPanelLabels;
  inputLabel: string;
  send: string;
  aiNotice: string;
  tooLong: string;
  failed: string;
  /** The account has started as many sessions as it may. */
  sessionLimit: string;
};

/**
 * Where a session starts: one field. The first message creates the session,
 * named from what it says, and the session's chat sends it as its first turn
 * (lib/first-message). Nothing exists before the send, and nothing typed is
 * lost when the session cannot be created. The field holds only what the user
 * writes: who they are and how much the wizard should ask are choices beside
 * it, told to the wizard as the first lines of the message that is sent
 * (lib/chat-background).
 */
export function StartView({ labels }: { labels: StartViewLabels }) {
  const { panel } = labels;
  const start = panel.start;
  const router = useRouter();
  const fieldId = useId();
  const noticeId = `${fieldId}-ai-notice`;
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The message is on its way: everything but the field steps back.
  const [leaving, setLeaving] = useState(false);
  const field = useRef<HTMLTextAreaElement>(null);
  const box = useRef<HTMLDivElement>(null);
  // Also in a ref: a second Enter arrives before the first has re-rendered.
  const sending = useRef(false);

  // Into the field, after what is already there (an example).
  const focusField = useCallback(() => {
    const el = field.current;
    if (!el) return;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  }, []);

  useEffect(() => {
    // Not on a touch screen, where the cursor would raise the keyboard.
    if (window.matchMedia("(pointer: fine)").matches) requestAnimationFrame(focusField);
    // "New session" pressed while this view is already open.
    window.addEventListener(FOCUS_START_EVENT, focusField);
    return () => window.removeEventListener(FOCUS_START_EVENT, focusField);
  }, [focusField]);

  const { background, chooseBackground, pace, choosePace, example, examplesShown, chooseExample } = useStartChips(
    input,
    setInput,
    panel,
    () => {
      field.current?.focus();
      requestAnimationFrame(focusField);
    },
  );

  async function send() {
    const text = input.trim();
    if (!text || sending.current) return;
    sending.current = true;
    setPending(true);
    setLeaving(true);
    setError(null);
    // Who the user is and how much to ask go ahead of their words, here and
    // not in the field.
    const message = withStartLines(text, startLines(panel, { background, pace }));
    const result = await startSessionFromMessage(message).catch(() => ({ error: "failed" as const }));
    if (!result || "error" in result) {
      // The words stay in the field, to send again.
      sending.current = false;
      setPending(false);
      setLeaving(false);
      if (result?.error !== "empty") {
        setError(
          result?.error === "too_long"
            ? labels.tooLong
            : result?.error === "session_limit"
              ? labels.sessionLimit
              : labels.failed,
        );
      }
      return;
    }
    // The field is not emptied: this view is left as it is for the session's
    // page, where the message appears as the conversation's first and the
    // chat's field starts from where this one stands.
    keepFirstMessage(result.id, { text: message, fieldTop: box.current?.getBoundingClientRect().top });
    router.push(`/sessions/${result.id}`);
  }

  const stepsBack = leaving || undefined;

  return (
    <>
      <div aria-hidden className="start-backdrop" data-leaving={stepsBack} />
      <div
        data-testid="start-view"
        className="relative z-10 mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center-safe px-3 pb-[10dvh] pt-14 sm:px-4"
      >
        <div className="start-in start-leaves" data-leaving={stepsBack}>
          <h1 className="flex flex-col items-center gap-4 text-center">
            {/* The logo's own drawing, at a size that names the product. It
                arrives once, as the view opens (.logo-arrive in globals.css). */}
            <span className="logo-arrive">
              <Image
                src="/gaik-wordmark.svg"
                alt="GAIK"
                width={882}
                height={303}
                priority
                unoptimized
                className="h-12 w-auto sm:h-16"
              />
            </span>
            <span className="text-[1.875rem] font-semibold leading-tight tracking-[-0.02em] text-text-strong">
              Solution Wizard
            </span>
          </h1>

          <div className="mt-9 px-1 pb-4 text-center" data-testid="chat-start">
            <h2 className="text-lg font-medium text-text">{start.title}</h2>
            <p className="mx-auto mt-1 max-w-prose text-balance text-sm leading-relaxed text-text-secondary">
              {start.lede}
            </p>
          </div>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <label htmlFor={fieldId} className="sr-only">
            {labels.inputLabel}
          </label>
          {/* The view's one control, and the one thing on it that is lifted off
              the page: the field, the two choices, and the send button. */}
          <ComposerCard
            fieldRef={field}
            boxRef={box}
            fieldId={fieldId}
            value={input}
            onChange={(value) => {
              setInput(value);
              setError(null);
            }}
            onEnter={() => void send()}
            // The choices' lines go in front of what is typed here.
            maxLength={MAX_CHAT_MESSAGE_CHARS - START_LINES_ROOM}
            readOnly={pending}
            placeholder={start.placeholder}
            describedBy={noticeId}
            large
            tools={
              <>
                <BackgroundChoice labels={panel} chosen={background} onChoose={chooseBackground} />
                <PaceChoice labels={panel} chosen={pace} onChoose={choosePace} />
              </>
            }
            sendLabel={labels.send}
            sendDisabled={pending}
            sendBusy={pending}
          />
          {error && (
            <p role="alert" data-testid="start-error" className="mt-2 px-1 text-sm text-danger-text">
              {error}
            </p>
          )}
          {/* Always in view: the replies come from an AI (AI Act art. 50(1)). */}
          <p
            id={noticeId}
            data-testid="chat-ai-notice"
            className="mt-1.5 px-1 text-center text-xs text-text-muted"
          >
            {labels.aiNotice}
          </p>
          {/* The examples sit under the field they fill. */}
          <div className="start-leaves mt-4" data-leaving={stepsBack}>
            <ExampleChips
              labels={start}
              chosen={example}
              offered={examplesShown}
              onChoose={chooseExample}
            />
          </div>
        </form>
      </div>
    </>
  );
}
