"use client";

import { useEffect, useRef } from "react";
import { Compartment, EditorState, type Extension } from "@codemirror/state";
import {
  Decoration,
  EditorView,
  drawSelection,
  highlightActiveLine,
  highlightActiveLineGutter,
  keymap,
  lineNumbers,
} from "@codemirror/view";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import {
  HighlightStyle,
  StreamLanguage,
  bracketMatching,
  indentOnInput,
  indentUnit,
  syntaxHighlighting,
} from "@codemirror/language";
import { tags } from "@lezer/highlight";
import type { EditorLanguage } from "@/lib/poc-file";
import { lockedRanges as lockedRangesExtension, lockedRangesField } from "@/lib/locked-ranges";

/**
 * The text editor of the PoC tab: CodeMirror 6 with the app's own colours.
 *
 * Loaded with `next/dynamic` by the file dialog, so the session page carries
 * none of it until a file is opened; each language is a chunk of its own,
 * fetched when a file of that kind is. The document is given once: the dialog
 * remounts the editor (a new `key`) to show another version of the file.
 * The full blueprint view's advanced editor uses it too, with the parts of
 * the text that cannot be edited (`lockedRanges`) shaded.
 */

// The app's tokens (app/globals.css), so the editor follows the theme.
const theme = EditorView.theme({
  "&": {
    height: "100%",
    color: "var(--color-text)",
    backgroundColor: "var(--color-surface)",
    fontSize: "13px",
  },
  "&.cm-focused": { outline: "none" },
  ".cm-scroller": {
    fontFamily: "var(--font-mono)",
    lineHeight: "1.55",
    scrollbarWidth: "thin",
    scrollbarColor: "var(--color-border-strong) transparent",
  },
  // The dialog's frame shows the focus; a ring around the text itself would
  // be drawn at the scroller's edge and clipped.
  ".cm-content": { caretColor: "var(--color-text-strong)", padding: "10px 0", boxShadow: "none" },
  ".cm-line": { padding: "0 12px" },
  ".cm-gutters": {
    backgroundColor: "var(--color-app)",
    color: "var(--color-text-muted)",
    borderRight: "1px solid var(--color-border)",
  },
  ".cm-lineNumbers .cm-gutterElement": { padding: "0 10px 0 12px", minWidth: "2.5rem" },
  ".cm-activeLine": { backgroundColor: "rgb(2 119 192 / 0.05)" },
  ".cm-activeLineGutter": { backgroundColor: "var(--color-surface-muted)", color: "var(--color-text)" },
  "&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, .cm-selectionBackground": {
    backgroundColor: "var(--color-brand-soft-border)",
  },
  ".cm-cursor": { borderLeftColor: "var(--color-text-strong)" },
  // A part of the text that cannot be edited (lockedRanges).
  ".cm-locked": { backgroundColor: "var(--color-surface-muted)", opacity: "0.75" },
  "&.cm-focused .cm-matchingBracket": {
    backgroundColor: "var(--color-brand-soft)",
    outline: "1px solid var(--color-brand-soft-border)",
  },
});

const lockedMark = Decoration.mark({ class: "cm-locked", attributes: { "data-locked": "true" } });
/** The locked ranges drawn shaded. */
const lockedDecorations = EditorView.decorations.compute([lockedRangesField], (state) => {
  const locked = state.field(lockedRangesField, false);
  if (!locked) return Decoration.none;
  const marks: ReturnType<typeof lockedMark.range>[] = [];
  locked.between(0, state.doc.length, (from, to) => {
    marks.push(lockedMark.range(from, to));
  });
  return Decoration.set(marks);
});

const highlight = HighlightStyle.define([
  { tag: [tags.comment, tags.meta], color: "var(--color-text-muted)", fontStyle: "italic" },
  {
    tag: [tags.keyword, tags.operatorKeyword, tags.modifier, tags.definitionKeyword],
    color: "var(--color-step-ai)",
  },
  { tag: [tags.string, tags.special(tags.string), tags.regexp], color: "var(--color-success-text)" },
  { tag: [tags.number, tags.bool, tags.null, tags.atom], color: "var(--color-step-human)" },
  {
    tag: [tags.function(tags.variableName), tags.definition(tags.variableName), tags.className, tags.typeName],
    color: "var(--color-brand-text)",
  },
  { tag: [tags.propertyName, tags.attributeName, tags.tagName], color: "var(--color-info-text)" },
  { tag: tags.heading, color: "var(--color-text-strong)", fontWeight: "600" },
  { tag: tags.strong, fontWeight: "600" },
  { tag: tags.emphasis, fontStyle: "italic" },
  { tag: [tags.link, tags.url], color: "var(--color-brand-text)", textDecoration: "underline" },
  { tag: tags.invalid, color: "var(--color-danger-text)" },
]);

async function languageExtension(language: EditorLanguage | null): Promise<Extension | null> {
  switch (language) {
    case "python":
      return (await import("@codemirror/lang-python")).python();
    case "json":
      return (await import("@codemirror/lang-json")).json();
    case "yaml":
      return (await import("@codemirror/lang-yaml")).yaml();
    case "markdown":
      return (await import("@codemirror/lang-markdown")).markdown();
    case "html":
      return (await import("@codemirror/lang-html")).html();
    case "css":
      return (await import("@codemirror/lang-css")).css();
    case "javascript":
      return (await import("@codemirror/lang-javascript")).javascript();
    case "toml":
      return StreamLanguage.define((await import("@codemirror/legacy-modes/mode/toml")).toml);
    case "properties":
      return StreamLanguage.define((await import("@codemirror/legacy-modes/mode/properties")).properties);
    default:
      return null;
  }
}

export default function CodeEditor({
  value,
  language,
  readOnly = false,
  lockedRanges,
  label,
  onChange,
  onSave,
}: {
  /** The document as the editor starts with it. */
  value: string;
  language: EditorLanguage | null;
  readOnly?: boolean;
  /** Parts of the starting document that cannot be edited; taken once, as `value` is. */
  lockedRanges?: readonly { from: number; to: number }[];
  /** What a screen reader calls the text field. */
  label: string;
  onChange?: (text: string) => void;
  /** Ctrl/Cmd+S. */
  onSave?: () => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  // The latest callbacks, without rebuilding the editor when the parent re-renders.
  const handlers = useRef({ onChange, onSave });
  useEffect(() => {
    handlers.current = { onChange, onSave };
  });

  useEffect(() => {
    const parent = host.current;
    if (!parent) return;
    const languageSlot = new Compartment();
    // Prose wraps; code keeps its lines and scrolls sideways.
    const wraps = language === "markdown" || language === null;
    const view = new EditorView({
      parent,
      state: EditorState.create({
        doc: value,
        extensions: [
          lineNumbers(),
          highlightActiveLineGutter(),
          highlightActiveLine(),
          drawSelection(),
          history(),
          indentOnInput(),
          bracketMatching(),
          indentUnit.of(language === "python" ? "    " : "  "),
          EditorState.tabSize.of(4),
          EditorState.readOnly.of(readOnly),
          EditorView.editable.of(!readOnly),
          ...(lockedRanges?.length ? [lockedRangesExtension(lockedRanges), lockedDecorations] : []),
          ...(wraps ? [EditorView.lineWrapping] : []),
          syntaxHighlighting(highlight),
          theme,
          languageSlot.of([]),
          EditorView.contentAttributes.of({
            "aria-label": label,
            // Shown, selectable and announced as read-only when it is.
            ...(readOnly ? { "aria-readonly": "true", tabindex: "0" } : {}),
            spellcheck: "false",
            autocapitalize: "off",
          }),
          keymap.of([
            {
              key: "Mod-s",
              preventDefault: true,
              run: () => {
                handlers.current.onSave?.();
                return true;
              },
            },
            ...defaultKeymap,
            ...historyKeymap,
            // Tab indents; Ctrl-M (defaultKeymap) hands Tab back to the page.
            indentWithTab,
          ]),
          EditorView.updateListener.of((update) => {
            if (update.docChanged) handlers.current.onChange?.(update.state.doc.toString());
          }),
        ],
      }),
    });
    let live = true;
    languageExtension(language)
      .then((extension) => {
        if (live && extension) view.dispatch({ effects: languageSlot.reconfigure(extension) });
      })
      .catch(() => {
        // Without its language the file is shown as plain text.
      });
    return () => {
      live = false;
      view.destroy();
    };
    // The document is taken once, at mount: see the component's comment.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [language, readOnly, label]);

  return <div ref={host} className="h-full min-h-0 overflow-hidden" data-testid="code-editor" />;
}
