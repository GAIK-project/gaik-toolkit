"use client";

import { useEffect, useLayoutEffect, type ReactNode, type RefObject } from "react";
import { fitField } from "@/lib/field-grow";
import { Icon } from "./icons";

/** The tallest the field grows to, in px (max-h-40); past it the text scrolls. */
const FIELD_MAX = 160;

/** The browser sizes the field to its text itself (field-sizing: content). */
function sizesItself(): boolean {
  return typeof CSS !== "undefined" && CSS.supports("field-sizing", "content");
}

/**
 * Keeps a field as tall as its text, up to `max` px, where the stylesheet
 * cannot (field-sizing: content): measured here (lib/field-grow) when the text
 * or the field's width changes. `deps` is what the height depends on.
 */
export function useGrowingField(
  fieldRef: RefObject<HTMLTextAreaElement | null>,
  max: number,
  deps: readonly unknown[],
) {
  // Measured before paint, so the box never shows a frame at the wrong height
  // when a message is sent.
  useLayoutEffect(() => {
    const el = fieldRef.current;
    if (!el || sizesItself()) return;
    fitField(el, max, borderHeight);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fieldRef, max, ...deps]);
  // And again when the field's width changes: a chat that was narrow for a
  // moment wraps the placeholder onto many lines.
  useEffect(() => {
    const el = fieldRef.current;
    if (!el || sizesItself() || typeof ResizeObserver === "undefined") return;
    let width = el.offsetWidth;
    const observer = new ResizeObserver(() => {
      if (el.offsetWidth === width) return;
      width = el.offsetWidth;
      fitField(el, max, borderHeight);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [fieldRef, max]);
}

/** The field's top and bottom borders, which scrollHeight leaves out. */
function borderHeight(el: Parameters<typeof fitField>[0]): number {
  const style = window.getComputedStyle(el as HTMLTextAreaElement);
  return parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);
}

/**
 * The message field: one card that holds the text and the send button. With
 * tools (the choices of a first message) they sit in a row under the text,
 * the button at its end; without them the button stands beside the text, so a
 * running conversation's field is one line tall until it is written in. The
 * start view and a session's chat draw the same card. Enter sends (the form's
 * submit), Shift+Enter breaks the line.
 *
 * The field is as tall as its text, up to FIELD_MAX. Where the browser cannot
 * size it from the stylesheet, it is measured here (lib/field-grow).
 */
export function ComposerCard({
  fieldRef,
  boxRef,
  fieldId,
  value,
  onChange,
  onEnter,
  placeholder,
  maxLength,
  describedBy,
  readOnly = false,
  large = false,
  tools,
  sendLabel,
  sendDisabled = false,
  sendBusy = false,
}: {
  fieldRef: RefObject<HTMLTextAreaElement | null>;
  /** The card itself: where the field stands on the page. */
  boxRef?: RefObject<HTMLDivElement | null>;
  fieldId: string;
  value: string;
  onChange: (value: string) => void;
  /** Enter without Shift. */
  onEnter: () => void;
  placeholder: string;
  maxLength: number;
  describedBy?: string;
  readOnly?: boolean;
  /** The start view's one control: larger text, two lines to begin with. */
  large?: boolean;
  /** What sits at the start of the tools row. */
  tools?: ReactNode;
  sendLabel: string;
  sendDisabled?: boolean;
  /** The message is on its way: the button turns. */
  sendBusy?: boolean;
}) {
  // Only where the stylesheet cannot do it. The placeholder counts too: a
  // longer one (a gate's change request) may wrap.
  useGrowingField(fieldRef, FIELD_MAX, [value, large, placeholder]);

  const empty = value.trim() === "";
  const send = (
    <button
      type="submit"
      disabled={sendDisabled}
      aria-busy={sendBusy || undefined}
      aria-label={sendLabel}
      title={sendLabel}
      // Quiet while there is nothing to send, filled once there is.
      data-empty={empty || undefined}
      className={`inline-flex shrink-0 items-center justify-center rounded-full transition-[background-color,color,transform,opacity] duration-150 ease-out active:scale-90 disabled:cursor-not-allowed disabled:opacity-40 disabled:active:scale-100 ${
        large ? "h-9 w-9" : "h-8 w-8"
      } ${
        empty
          ? "bg-surface-muted text-text-muted"
          : "bg-brand text-on-brand hover:bg-brand-hover active:bg-brand-active"
      }`}
    >
      <Icon
        name={sendBusy ? "loaderCircle" : "arrowUp"}
        size={18}
        className={sendBusy ? "animate-spin motion-reduce:animate-none" : ""}
      />
    </button>
  );
  return (
    <div
      ref={boxRef}
      // A choice's menu hangs from the card, over it (components/chat-start).
      className={`relative flex ${tools ? "flex-col" : "items-end gap-1"} rounded-2xl border border-border-strong bg-surface transition-[border-color,box-shadow] duration-150 focus-within:border-brand focus-within:ring-3 focus-within:ring-brand/25 ${
        large ? "p-2 shadow-md" : "p-1.5 shadow-sm"
      }`}
    >
      <textarea
        ref={fieldRef}
        id={fieldId}
        name="message"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          // Enter sends; Shift+Enter inserts a newline.
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            onEnter();
          }
        }}
        rows={large ? 2 : 1}
        maxLength={maxLength}
        readOnly={readOnly}
        autoComplete="off"
        placeholder={placeholder}
        aria-describedby={describedBy}
        className={`scroll-thin field-sizing-content max-h-40 w-full min-w-0 resize-none overflow-y-auto border-0 bg-transparent px-2 py-1.5 text-text placeholder:text-text-muted focus-in-box focus:outline-none ${
          large ? "min-h-15 text-base" : "min-h-8 text-sm"
        }`}
      />
      {tools ? (
        <div className="flex min-h-9 items-center gap-2 pl-0.5 pt-1">
          {/* A container: a tool gives up its label for its icon when the row is narrow. */}
          <div className="@container flex min-w-0 flex-1 items-center gap-2">{tools}</div>
          {send}
        </div>
      ) : (
        send
      )}
    </div>
  );
}
