"use client";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Plus, RotateCcw, X } from "lucide-react";
import {
  newItem,
  type PromptState,
  TEMPLATES,
  type Segment,
  type UseCaseMode,
} from "./prompt-template";

// What marks a part the user can change. Everything else is fixed instruction text.
const editable =
  "bg-primary/10 ring-primary/30 focus-within:ring-primary/60 rounded-md ring-1 transition-shadow";

const bare =
  "placeholder:text-muted-foreground/60 bg-transparent outline-none field-sizing-content";

/** One step of the prompt: its fixed text, or an editable value or list. */
function EditableSegment({
  segment,
  state,
  disabled,
  onChange,
}: {
  segment: Extract<Segment, { type: "token" | "list" }>;
  state: PromptState;
  disabled: boolean;
  onChange: (next: PromptState) => void;
}) {
  if (segment.type === "token") {
    const value = state.tokens[segment.key] ?? "";
    return (
      <span className={cn(editable, "mx-0.5 inline-flex px-1.5 py-0.5")}>
        <input
          value={value}
          disabled={disabled}
          aria-label={segment.label}
          title={segment.label}
          size={Math.max(value.length, 2)}
          onChange={(e) =>
            onChange({
              ...state,
              tokens: { ...state.tokens, [segment.key]: e.target.value },
            })
          }
          className={cn(bare, "min-w-6 font-medium")}
        />
      </span>
    );
  }

  const items = state.lists[segment.key] ?? [];
  const setItems = (next: typeof items) =>
    onChange({ ...state, lists: { ...state.lists, [segment.key]: next } });
  const update = (id: string, text: string) =>
    setItems(
      items.map((item) =>
        item.id === id ? { ...item, text, fresh: false } : item,
      ),
    );
  const remove = (id: string) => setItems(items.filter((i) => i.id !== id));
  const add = () => setItems([...items, newItem()]);

  if (segment.style === "bullets") {
    return (
      <ul className="my-2 space-y-1.5">
        {items.map((item) => (
          <li key={item.id} className="flex items-center gap-2">
            <span aria-hidden className="text-muted-foreground">
              -
            </span>
            <span className={cn(editable, "flex min-w-0 flex-1 items-center")}>
              <input
                value={item.text}
                disabled={disabled}
                autoFocus={item.fresh}
                aria-label={segment.label}
                placeholder="Field name (optional details in brackets)"
                onChange={(e) => update(item.id, e.target.value)}
                className={cn(bare, "min-w-0 flex-1 px-2 py-1")}
              />
              <button
                type="button"
                disabled={disabled}
                onClick={() => remove(item.id)}
                className="hover:bg-primary/15 mr-1 rounded-full p-1"
                aria-label={`Remove ${item.text || "field"}`}
              >
                <X className="size-3.5" />
              </button>
            </span>
          </li>
        ))}
        <li>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={disabled}
            onClick={add}
            className="text-primary h-7 px-2"
          >
            <Plus className="mr-1 size-3.5" />
            {segment.label}
          </Button>
        </li>
      </ul>
    );
  }

  return (
    <span className="inline-flex flex-wrap items-center gap-1 align-middle">
      {items.map((item) => (
        <span
          key={item.id}
          className={cn(editable, "inline-flex items-center pl-2")}
        >
          <input
            value={item.text}
            disabled={disabled}
            autoFocus={item.fresh}
            aria-label={segment.label}
            placeholder="New"
            size={Math.max(item.text.length, 3)}
            onChange={(e) => update(item.id, e.target.value)}
            className={cn(bare, "min-w-8 py-0.5")}
          />
          <button
            type="button"
            disabled={disabled}
            onClick={() => remove(item.id)}
            className="hover:bg-primary/15 mx-1 rounded-full p-0.5"
            aria-label={`Remove ${item.text || "item"}`}
          >
            <X className="size-3" />
          </button>
        </span>
      ))}
      <button
        type="button"
        disabled={disabled}
        onClick={add}
        title={segment.label}
        aria-label={segment.label}
        className="text-primary border-primary/40 hover:bg-primary/10 inline-flex size-6 items-center justify-center rounded-md border border-dashed"
      >
        <Plus className="size-3.5" />
      </button>
    </span>
  );
}

/** A sentence of the prompt that can be removed, and brought back. */
function OptionalSentence({
  segment,
  state,
  disabled,
  onChange,
}: {
  segment: Extract<Segment, { type: "optional" }>;
  state: PromptState;
  disabled: boolean;
  onChange: (next: PromptState) => void;
}) {
  const setRemoved = (removed: boolean) =>
    onChange({
      ...state,
      removed: { ...state.removed, [segment.key]: removed },
    });

  return (
    <div className="mt-3">
      {state.removed[segment.key] ? (
        <button
          type="button"
          disabled={disabled}
          onClick={() => setRemoved(false)}
          className="text-muted-foreground/80 border-primary/40 hover:bg-primary/10 inline-flex max-w-full items-center gap-1.5 rounded-md border border-dashed px-2 py-1 text-left line-through"
          title="Put this sentence back"
        >
          <Plus className="text-primary size-3.5 shrink-0 no-underline" />
          {segment.text}
        </button>
      ) : (
        <span
          className={cn(
            editable,
            "text-foreground/80 inline-flex max-w-full items-center gap-2 py-1 pr-1 pl-2",
          )}
        >
          {segment.text}
          <button
            type="button"
            disabled={disabled}
            onClick={() => setRemoved(true)}
            className="hover:bg-primary/15 shrink-0 rounded-full p-1"
            aria-label={`Remove: ${segment.text}`}
            title="Remove this sentence"
          >
            <X className="size-3.5" />
          </button>
        </span>
      )}
    </div>
  );
}

/**
 * The starting prompt of a case with its changeable parts highlighted. Text, values
 * and lists of fields can be edited in place; the grey text is fixed.
 */
export function PromptEditor({
  mode,
  state,
  disabled,
  onChange,
  onReset,
}: {
  mode: UseCaseMode;
  state: PromptState;
  disabled: boolean;
  onChange: (next: PromptState) => void;
  onReset: () => void;
}) {
  const { segments } = TEMPLATES[mode];
  const hasBlocks = segments.some(
    (segment) => segment.type === "list" && segment.style === "bullets",
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <p className="text-muted-foreground flex flex-wrap items-center gap-2">
          <span className={cn(editable, "px-2 py-0.5 font-medium")}>
            Highlighted
          </span>
          parts are yours to edit, add to or remove. Grey text is fixed.
        </p>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={disabled}
          onClick={onReset}
          className="h-7"
        >
          <RotateCcw className="mr-1 size-3.5" />
          Restore the original prompt
        </Button>
      </div>
      <div
        className={cn(
          "text-muted-foreground rounded-lg border p-4 text-sm",
          hasBlocks ? "space-y-0" : "leading-8",
        )}
      >
        {segments.map((segment, index) => {
          if (segment.type === "text") {
            // In the block layout every paragraph stands on its own line, so the
            // line breaks around the text are dropped.
            const text = hasBlocks
              ? segment.text.replace(/^\n+|\n+$/g, "")
              : segment.text;
            if (!text) return null;
            return hasBlocks ? (
              <p key={index} className="mt-3 whitespace-pre-line first:mt-0">
                {text}
              </p>
            ) : (
              <span key={index} className="whitespace-pre-line">
                {text}
              </span>
            );
          }
          if (segment.type === "optional") {
            return (
              <OptionalSentence
                key={index}
                segment={segment}
                state={state}
                disabled={disabled}
                onChange={onChange}
              />
            );
          }
          return (
            <EditableSegment
              key={index}
              segment={segment}
              state={state}
              disabled={disabled}
              onChange={onChange}
            />
          );
        })}
      </div>
    </div>
  );
}
