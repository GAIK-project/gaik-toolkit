"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { renderMarkdown } from "@/lib/markdown";
import type { ChatActivityLabels } from "@/lib/chat-activity";
import { cardPlacement, withComponentLinks } from "@/lib/component-links";
import { Icon } from "./icons";

let mermaidReady: Promise<typeof import("mermaid").default> | null = null;

// Mermaid is large, so it loads only when a message has a diagram. Strict mode
// keeps the diagram text from adding scripts or links, and a diagram that does
// not parse throws instead of drawing an error picture into the page.
function loadMermaid() {
  mermaidReady ??= import("mermaid").then(({ default: mermaid }) => {
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      theme: "neutral",
      fontFamily: "inherit",
      suppressErrorRendering: true,
      // What a diagram's own text may not set, in a directive or in front
      // matter, at any depth: mermaid's defaults, and the keys that add CSS or
      // HTML labels.
      secure: [
        "secure",
        "securityLevel",
        "startOnLoad",
        "maxTextSize",
        "suppressErrorRendering",
        "maxEdges",
        "themeCSS",
        "themeVariables",
        "fontFamily",
        "altFontFamily",
        "htmlLabels",
      ],
      // Natural size: scaled to the chat's width, a wide flowchart's labels
      // shrank to 9 px. The figure scrolls sideways instead.
      flowchart: { useMaxWidth: false },
      sequence: { useMaxWidth: false },
      class: { useMaxWidth: false },
      state: { useMaxWidth: false },
      er: { useMaxWidth: false },
      gantt: { useMaxWidth: false },
      journey: { useMaxWidth: false },
    });
    return mermaid;
  });
  return mermaidReady;
}

let diagramCount = 0;

// A diagram is drawn with the chat's settings only: its `%%{init: ...}%%`
// directives are taken out before mermaid reads it.
const MERMAID_DIRECTIVE = /%%\{[\s\S]*?\}%%/g;
export const withoutDirectives = (source: string) => source.replace(MERMAID_DIRECTIVE, "");

// Whether the figure's picture is cut off, measured again whenever its box
// changes size: a diagram drawn while the chat is out of sight measures 0, and
// the chat's width changes what fits.
function markClipping(picture: HTMLElement) {
  const figure = picture.closest(".chat-diagram");
  if (!figure || (picture.clientHeight === 0 && picture.clientWidth === 0)) return;
  const tall = picture.scrollHeight > picture.clientHeight + 1;
  const wide = picture.scrollWidth > picture.clientWidth + 1;
  figure.classList.toggle("is-clipped", tall);
  // A picture that is all in view needs no button to open it whole.
  figure.classList.toggle("is-whole", !tall && !wide);
}

type DiagramLabels = Pick<
  ChatActivityLabels,
  "diagram" | "diagramSteps" | "diagramDrawing" | "diagramExpand" | "diagramClose"
> &
  // Without these words a component's name stays plain text.
  Partial<Pick<ChatActivityLabels, "components">>;

const NO_LABELS: DiagramLabels = {
  diagram: "",
  diagramSteps: "",
  diagramDrawing: "",
  diagramExpand: "",
  diagramClose: "",
};

const escapeText = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const MERMAID_BLOCK = /<pre><code class="language-mermaid">[\s\S]*?<\/code><\/pre>/g;

// A ```mermaid block is never shown as code while it can still become a
// picture: while the reply streams, and while mermaid loads and draws, a short
// line stands in for it. The code stays in the page, hidden, for the drawing
// and for a block that turns out not to be a diagram.
function withPendingDiagrams(html: string, drawing: string): string {
  return html.replace(
    MERMAID_BLOCK,
    (block) =>
      `<div class="chat-diagram-pending" data-testid="chat-diagram-pending">` +
      `<p class="chat-diagram-drawing">${escapeText(drawing)}</p>` +
      `${block.replace("<pre>", "<pre hidden>")}</div>`,
  );
}

// A block that is not a diagram after all goes back to being code.
function showAsCode(pending: Element) {
  const pre = pending.querySelector("pre");
  if (!pre) return;
  pre.hidden = false;
  pending.replaceWith(pre);
}

// The boxes' labels in the order the diagram defines them, for its accessible
// name; mermaid draws the nodes of a flowchart in that order.
function nodeLabels(svg: Element | null): string[] {
  if (!svg) return [];
  const seen = new Set<string>();
  for (const node of svg.querySelectorAll("g.node")) {
    const text = (node.textContent ?? "").replace(/\s+/g, " ").trim();
    if (text) seen.add(text);
  }
  return [...seen];
}

function figureFor(svg: string, labels: DiagramLabels): HTMLElement {
  const figure = document.createElement("figure");
  figure.className = "chat-diagram";
  figure.dataset.testid = "chat-diagram";
  const picture = document.createElement("div");
  picture.className = "chat-diagram-picture";
  picture.setAttribute("role", "img");
  picture.innerHTML = svg;
  const drawn = picture.querySelector("svg");
  // One image with one name: the steps in order, read out instead of boxes and arrows.
  drawn?.setAttribute("aria-hidden", "true");
  const steps = nodeLabels(drawn);
  const name = steps.length && labels.diagramSteps ? labels.diagramSteps.replace("{steps}", () => steps.join(", ")) : labels.diagram;
  if (name) picture.setAttribute("aria-label", name);
  const bar = document.createElement("div");
  bar.className = "chat-diagram-bar";
  const expand = document.createElement("button");
  expand.type = "button";
  expand.className = "chat-diagram-expand";
  expand.dataset.diagramExpand = "";
  expand.dataset.testid = "chat-diagram-expand";
  // The zoom-in icon of components/icons (Lucide), drawn here because the
  // figure is built outside React.
  expand.innerHTML =
    '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="11" cy="11" r="8"/><line x1="21" x2="16.65" y1="21" y2="16.65"/><line x1="11" x2="11" y1="8" y2="14"/><line x1="8" x2="14" y1="11" y2="11"/></svg>' +
    `<span>${escapeText(labels.diagramExpand)}</span>`;
  bar.append(expand);
  figure.append(picture, bar);
  return figure;
}

type FullSize = { markup: { __html: string }; name: string };

// --- A GAIK component's name and its card (lib/component-links) -----------
// The card shows on hover (CSS) and on keyboard focus, and stays open after a
// press, which is how it opens on a touch screen. It is placed here, in
// viewport pixels, so a table that scrolls sideways does not cut it off.

const componentOf = (target: EventTarget | null) =>
  target instanceof Element ? target.closest<HTMLElement>(".cmp") : null;

/** The nearest box that scrolls up and down: the conversation. */
function scrollerOf(el: HTMLElement): HTMLElement | null {
  for (let box = el.parentElement; box; box = box.parentElement) {
    if (/(auto|scroll)/.test(window.getComputedStyle(box).overflowY)) return box;
  }
  return null;
}

/** Puts a shown card by its name; false when the name has scrolled out of the conversation. */
function placeCard(cmp: HTMLElement): boolean {
  const card = cmp.querySelector<HTMLElement>(".cmp-card");
  const name = cmp.querySelector<HTMLElement>(".cmp-name");
  const body = cmp.closest<HTMLElement>(".chat-md-body");
  if (!card || !name || !body || card.offsetWidth === 0) return true;
  const column = body.getBoundingClientRect();
  const list = scrollerOf(body)?.getBoundingClientRect();
  const within = {
    left: Math.max(column.left, 8),
    right: Math.min(column.right, window.innerWidth - 8),
    top: Math.max(list?.top ?? 0, 0),
    bottom: Math.min(list?.bottom ?? window.innerHeight, window.innerHeight),
  };
  const at = name.getBoundingClientRect();
  if (at.bottom < within.top || at.top > within.bottom) return false;
  // Its own width (globals.css), or the column's when that is narrower.
  card.style.maxWidth = `min(18rem, ${within.right - within.left}px)`;
  // Where the card's own (0, 0) is: the window, unless something around the
  // chat makes itself the frame of fixed boxes (a transform, a container).
  card.style.left = "0px";
  card.style.top = "0px";
  const origin = card.getBoundingClientRect();
  const to = cardPlacement(at, { width: origin.width, height: origin.height }, within);
  card.style.left = `${to.left - origin.left}px`;
  card.style.top = `${to.top - origin.top}px`;
  return true;
}

/** Closes a card the reader pressed open. */
function unpin(cmp: Element) {
  cmp.removeAttribute("data-open");
}

/** The figure's picture again, with its own ids so the two copies' arrowheads and styles do not collide. */
function fullSizeCopy(figure: Element): FullSize | null {
  const picture = figure.querySelector(".chat-diagram-picture");
  const svg = picture?.querySelector("svg");
  if (!picture || !svg) return null;
  const id = svg.id;
  const html = id ? svg.outerHTML.split(id).join(`${id}-full`) : svg.outerHTML;
  return { markup: { __html: html }, name: picture.getAttribute("aria-label") ?? "" };
}

// An assistant message as HTML. Once the message is complete, its ```mermaid
// blocks are drawn as diagrams (the agent describes workflows that way), capped
// in height with a button that opens the full picture; a block that does not
// parse stays as code. Links within the app open through the router.
export function ChatMarkdown({
  content,
  final,
  labels = NO_LABELS,
}: {
  content: string;
  /** False while the message is still streaming: a half diagram does not parse. */
  final: boolean;
  labels?: DiagramLabels;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const drawing = labels.diagramDrawing;
  // The same words are the same object: the page hands over a new labels
  // object with every render, and a new one here would write the message again
  // (see below), closing an open card.
  const componentWords = JSON.stringify(labels.components ?? null);
  const componentLabels = useMemo(
    () => (JSON.parse(componentWords) as ChatActivityLabels["components"] | null) ?? undefined,
    [componentWords],
  );
  const cardId = useId();
  // One object per content: React 19 writes innerHTML again whenever this prop
  // is a new object, which on every render (each streamed token of any message)
  // threw away a drawn diagram and the reader's text selection.
  const markup = useMemo(
    () => ({
      __html: withPendingDiagrams(withComponentLinks(renderMarkdown(content), componentLabels, cardId), drawing),
    }),
    [content, drawing, componentLabels, cardId],
  );
  const hasComponents = markup.__html.includes('class="cmp"');
  // The component whose card is showing: it follows its name when the
  // conversation scrolls, and a press elsewhere closes it.
  const shown = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!hasComponents) return;
    const onScroll = () => {
      const cmp = shown.current;
      if (!cmp?.isConnected) return;
      if (!placeCard(cmp)) {
        unpin(cmp);
        cmp.setAttribute("data-dismissed", "");
      }
    };
    const onPress = (e: PointerEvent) => {
      const root = ref.current;
      if (!root) return;
      const pressed = componentOf(e.target);
      for (const open of root.querySelectorAll(".cmp[data-open]")) {
        if (open !== pressed) unpin(open);
      }
    };
    // Capture: the conversation's scroll does not bubble.
    document.addEventListener("scroll", onScroll, true);
    document.addEventListener("pointerdown", onPress);
    return () => {
      document.removeEventListener("scroll", onScroll, true);
      document.removeEventListener("pointerdown", onPress);
    };
  }, [hasComponents]);

  function showCard(cmp: HTMLElement) {
    shown.current = cmp;
    placeCard(cmp);
  }
  /** The pointer or the focus has left the component: Esc no longer holds its card shut. */
  function leftComponent(e: { target: EventTarget | null; relatedTarget: EventTarget | null }) {
    const cmp = componentOf(e.target);
    if (!cmp || (e.relatedTarget instanceof Node && cmp.contains(e.relatedTarget))) return;
    cmp.removeAttribute("data-dismissed");
    cmp.removeAttribute("data-focus");
  }
  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key !== "Escape") return;
    const cmp = componentOf(e.target);
    if (!cmp) return;
    // Esc closes the card and leaves the focus on the name.
    unpin(cmp);
    cmp.setAttribute("data-dismissed", "");
    cmp.querySelector<HTMLElement>(".cmp-name")?.focus();
  }
  // Watches the drawn pictures' sizes for as long as the message is on the page.
  const sizes = useRef<ResizeObserver | null>(null);
  useEffect(() => {
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) markClipping(entry.target as HTMLElement);
    });
    sizes.current = observer;
    return () => {
      observer.disconnect();
      sizes.current = null;
    };
  }, []);
  useEffect(() => {
    if (!final || !ref.current?.querySelector(".chat-diagram-pending")) return;
    let cancelled = false;
    void (async () => {
      let mermaid: Awaited<ReturnType<typeof loadMermaid>>;
      try {
        mermaid = await loadMermaid();
      } catch {
        mermaidReady = null; // try again with the next message
        if (!cancelled) ref.current?.querySelectorAll(".chat-diagram-pending").forEach(showAsCode);
        return;
      }
      // Look the blocks up only now: while mermaid loaded, React may have
      // written the message's HTML again, which leaves earlier nodes detached.
      const root = ref.current;
      if (cancelled || !root) return;
      for (const pending of root.querySelectorAll(".chat-diagram-pending")) {
        if (cancelled || !pending.isConnected) return;
        const source = withoutDirectives(pending.querySelector("code.language-mermaid")?.textContent ?? "");
        try {
          if (!(await mermaid.parse(source, { suppressErrors: true }))) {
            showAsCode(pending);
            continue;
          }
          const { svg } = await mermaid.render(`chat-diagram-${++diagramCount}`, source);
          if (cancelled || !pending.isConnected) return;
          const figure = figureFor(svg, labels);
          pending.replaceWith(figure);
          const picture = figure.querySelector<HTMLElement>(".chat-diagram-picture");
          if (picture) {
            markClipping(picture);
            sizes.current?.observe(picture);
          }
        } catch {
          showAsCode(pending);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [markup, final, labels]);

  // The full-size picture, in a modal dialog: the page behind it is inert, so
  // focus stays inside, and Esc closes it.
  const [expanded, setExpanded] = useState<FullSize | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = dialogRef.current;
    if (expanded && dialog && !dialog.open) dialog.showModal();
  }, [expanded]);

  function onClick(e: React.MouseEvent<HTMLDivElement>) {
    const target = e.target as Element;
    const name = target.closest<HTMLElement>(".cmp-name");
    if (name) {
      // A press keeps the card open until the next press: on a touch screen
      // there is no hover to open it.
      const cmp = name.parentElement!;
      cmp.removeAttribute("data-dismissed");
      cmp.toggleAttribute("data-open");
      showCard(cmp);
      return;
    }
    const expand = target.closest<HTMLElement>("[data-diagram-expand]");
    if (expand) {
      const figure = expand.closest(".chat-diagram");
      const copy = figure && fullSizeCopy(figure);
      if (copy) {
        openerRef.current = expand;
        setExpanded(copy);
      }
      return;
    }
    // A link within the app (lib/markdown keeps these in the same tab) goes
    // through the router, so the session page does not load again from scratch.
    const link = target.closest<HTMLAnchorElement>('a[href^="/"]');
    if (!link || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    router.push(link.getAttribute("href")!);
  }

  return (
    <>
      <div
        ref={ref}
        className="chat-md-body"
        onClick={onClick}
        onKeyDown={hasComponents ? onKeyDown : undefined}
        onMouseOver={
          hasComponents
            ? (e) => {
                const cmp = componentOf(e.target);
                if (cmp && cmp !== componentOf(e.relatedTarget)) showCard(cmp);
              }
            : undefined
        }
        onMouseOut={hasComponents ? leftComponent : undefined}
        onFocus={
          hasComponents
            ? (e) => {
                const cmp = componentOf(e.target);
                if (!cmp) return;
                // Kept on the component while the focus is anywhere in it: a
                // card shown by :focus-visible alone closed as the focus left
                // the name, before it could reach the card's link.
                if (e.target.matches(":focus-visible")) cmp.setAttribute("data-focus", "");
                showCard(cmp);
              }
            : undefined
        }
        onBlur={hasComponents ? leftComponent : undefined}
        dangerouslySetInnerHTML={markup}
      />
      {expanded && (
        <dialog
          ref={dialogRef}
          aria-labelledby={titleId}
          data-testid="chat-diagram-dialog"
          className="chat-diagram-dialog"
          onClose={() => {
            setExpanded(null);
            openerRef.current?.focus();
          }}
          // A click on the backdrop (the dialog element itself) closes it.
          onClick={(e) => {
            if (e.target === e.currentTarget) e.currentTarget.close();
          }}
        >
          <div className="flex items-center justify-between gap-3 border-b border-border py-2 pl-4 pr-2">
            <h2 id={titleId} className="text-sm font-semibold text-text">
              {labels.diagram}
            </h2>
            <button
              type="button"
              onClick={() => dialogRef.current?.close()}
              aria-label={labels.diagramClose}
              title={labels.diagramClose}
              className="icon-btn"
            >
              <Icon name="x" size={18} />
            </button>
          </div>
          <div
            className="chat-diagram-full scroll-thin"
            role="img"
            aria-label={expanded.name || labels.diagram}
            dangerouslySetInnerHTML={expanded.markup}
          />
        </dialog>
      )}
    </>
  );
}
