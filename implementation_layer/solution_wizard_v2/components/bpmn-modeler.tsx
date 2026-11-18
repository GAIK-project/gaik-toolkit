"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import type Modeler from "bpmn-js/lib/Modeler";
import type NavigatedViewer from "bpmn-js/lib/NavigatedViewer";
import {
  applyBpmnStartView,
  centerBpmnElement,
  fitBpmnView,
  reapplyBpmnView,
  zoomBpmnAroundCenter,
  type BpmnViewInset,
  type BpmnViewMode,
} from "@/lib/bpmn-view-fit";
import { BPMN_VIEWER_OPTIONS } from "@/lib/bpmn-viewer-options";
import { isRenamableBpmnElement, stripTaskCodePrefixes } from "@/lib/bpmn-edit-state";
import { gaikEditorModule, type BpmnEditorLabels, type BpmnEditorOps } from "@/lib/bpmn-editor-module";
import minimapModule from "diagram-js-minimap";
import "bpmn-js/dist/assets/diagram-js.css";
import "bpmn-js/dist/assets/bpmn-js.css";
import "bpmn-js/dist/assets/bpmn-font/css/bpmn-embedded.css";
import "diagram-js-minimap/assets/diagram-js-minimap.css";

type EventBus = {
  on: (event: string, cb: (e: unknown) => void) => void;
  off: (event: string, cb: (e: unknown) => void) => void;
  fire: (event: string) => void;
};

type DiagramElement = {
  id: string;
  type: string;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  labelTarget?: DiagramElement;
  businessObject?: { id?: string; name?: string; $type?: string; documentation?: { text?: string }[] };
  incoming?: { id: string }[];
  outgoing?: { id: string }[];
};

type Selection = {
  get: () => DiagramElement[];
  select: (element: DiagramElement | null) => void;
};

type Canvas = {
  zoom: () => number;
  viewbox: (box?: { x: number; y: number; width: number; height: number }) => {
    x: number;
    y: number;
    width: number;
    height: number;
  };
};

type ElementRegistry = {
  get: (id: string) => DiagramElement | undefined;
  filter: (fn: (el: DiagramElement) => boolean) => DiagramElement[];
};

type DirectEditing = { isActive: () => boolean };
type Dragging = { context: () => unknown };

/** The canvas: bpmn-js's modeler, or its viewer while the diagram is read-only. */
type BpmnCanvas = Modeler | NavigatedViewer;

/** The element whose properties the panel shows: only what a save lets the user rename. */
export type BpmnSelectionInfo = {
  id: string;
  /** bpmn type without the "bpmn:" prefix ("ServiceTask"). */
  type: string;
  name: string;
  /** The element's `<bpmn:documentation>`: a step's description, as the generator draws it. */
  documentation: string;
} | null;

/** The text of an element's `<bpmn:documentation>`, "" without one. */
function documentationOf(el: DiagramElement | undefined): string {
  const docs = el?.businessObject?.documentation;
  return Array.isArray(docs) ? docs.map((d) => d?.text ?? "").join("\n") : "";
}

export type BpmnModelerHandle = {
  zoomIn: () => void;
  zoomOut: () => void;
  fit: () => void;
  /**
   * Select an element and bring it to the middle of the view; false if it is
   * not on the canvas. `cover` is what a panel over the canvas hides, in screen px.
   */
  focusElement: (id: string, cover?: Partial<BpmnViewInset>) => boolean;
  /**
   * The user is in the middle of an edit that is no command yet: typing a
   * label in place, or dragging. An import now would throw it away.
   */
  isEditing: () => boolean;
  /** The mapping or the steps behind `ops` changed: the tools and the derived marks are drawn again. */
  refreshOps: () => void;
  /** Open or close the large view (`onToggleFullscreen`): the diagram over the whole screen. */
  toggleFullscreen: () => void;
  /** The `<bpmn:documentation>` of the element `id` on the canvas (a step's description); null when it is not there. */
  documentationOf: (id: string) => string | null;
  /** The lanes on the canvas, top to bottom: their element ids and names. */
  lanes: () => { id: string; name: string }[];
  /** The ids of the flows that start or end at the element `id`. */
  edgesOf: (id: string) => string[];
};

function selectionFromModeler(modeler: BpmnCanvas): BpmnSelectionInfo {
  try {
    const selected = (modeler.get("selection") as Selection).get?.() ?? [];
    if (selected.length !== 1) return null;
    const el = selected[0].labelTarget ?? selected[0];
    const bo = el.businessObject;
    const type = bo?.$type || el.type || "";
    const id = bo?.id || el.id;
    if (!isRenamableBpmnElement(type, id)) return null;
    return { id, type: type.replace(/^bpmn:/, ""), name: bo?.name || "", documentation: documentationOf(el) };
  } catch {
    return null;
  }
}

/**
 * The Workflow tab's BPMN diagram. One bpmn-js modeler lives as long as the
 * component; a new `xml` is imported into it, keeping the user's view and
 * selection, so an edit does not throw the diagram back to its start view.
 * Edits go out as operations through `ops` (lib/bpmn-editor-module).
 *
 * `readOnly` draws the same diagram in bpmn-js's viewer instead: it has no
 * modeling at all (no palette, context pad, dragging or typing in place), so
 * nothing on a locked canvas can change the process. The view and the
 * selection are carried over when the one takes the other's place.
 */
export const BpmnModeler = forwardRef<
  BpmnModelerHandle,
  {
    xml: string;
    ariaLabel: string;
    loadErrorLabel: string;
    editorLabels: BpmnEditorLabels;
    /** Where the editor's edits go; read when one is made. */
    ops?: BpmnEditorOps | null;
    className?: string;
    onSelectionChange?: (info: BpmnSelectionInfo) => void;
    onZoomChange?: (zoom: number) => void;
    /** A name is being typed in place on the canvas (true), or that has ended (false). */
    onDirectEditingChange?: (active: boolean) => void;
    /** After each import, when the diagram is on the canvas. */
    onImported?: () => void;
    /** After an edit in place or a drag has ended, with or without a change (see `isEditing`). */
    onEditingEnd?: () => void;
    /** A new value imports `xml` again even when the text is the same (after an edit was refused). */
    importKey?: number;
    /** The diagram can be looked at, moved and its elements picked, but not changed. */
    readOnly?: boolean;
    /** The minimap's name for a screen reader, in the UI language. */
    minimapLabel?: string;
    /** Whoever owns the large view opens or closes it (`toggleFullscreen`). */
    onToggleFullscreen?: () => void;
  }
>(function BpmnModeler(
  {
    xml,
    ariaLabel,
    loadErrorLabel,
    editorLabels,
    ops = null,
    className = "",
    onSelectionChange,
    onZoomChange,
    onDirectEditingChange,
    onImported,
    onEditingEnd,
    importKey = 0,
    readOnly = false,
    minimapLabel,
    onToggleFullscreen,
  },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const modelerRef = useRef<BpmnCanvas | null>(null);
  const callbacks = useRef({
    onSelectionChange,
    onZoomChange,
    onDirectEditingChange,
    onImported,
    onEditingEnd,
    onToggleFullscreen,
  });
  callbacks.current = {
    onSelectionChange,
    onZoomChange,
    onDirectEditingChange,
    onImported,
    onEditingEnd,
    onToggleFullscreen,
  };
  const labelsRef = useRef(editorLabels);
  labelsRef.current = editorLabels;
  const opsRef = useRef(ops);
  opsRef.current = ops;
  const [modeler, setModeler] = useState<BpmnCanvas | null>(null);
  const [error, setError] = useState(false);
  const [ready, setReady] = useState(false);

  const viewMode = useRef<BpmnViewMode>("start");
  // True while this component moves the view itself; any other change of the
  // view (wheel, drag, keys) is the user's, and a resize then keeps it.
  const programmatic = useRef(false);
  const importedOnce = useRef(false);
  // An import clears the selection before it is put back: the panel must not
  // close the name field under the user's cursor for that moment.
  const importing = useRef(false);
  // The view and the selection of the canvas that was just replaced by the
  // other kind ("Muokkaa" on a locked diagram): the new one opens on them.
  const carried = useRef<{ viewbox: ReturnType<Canvas["viewbox"]>; selected: string | null } | null>(null);

  /** What the palette (left) and the zoom controls (top) cover of the canvas, in screen px. */
  function viewInset(): BpmnViewInset {
    const palette = containerRef.current?.querySelector<HTMLElement>(".djs-palette");
    const left = palette && palette.offsetWidth > 0 ? palette.offsetLeft + palette.offsetWidth + 12 : 16;
    return { left, top: 56, right: 16, bottom: 16 };
  }

  function moveView(fn: () => void) {
    programmatic.current = true;
    try {
      fn();
    } catch {
      /* tearing down */
    } finally {
      programmatic.current = false;
    }
    const m = modelerRef.current;
    if (m) callbacks.current.onZoomChange?.((m.get("canvas") as Canvas).zoom());
  }

  useImperativeHandle(
    ref,
    () => ({
      zoomIn: () => {
        const m = modelerRef.current;
        const container = containerRef.current;
        if (!m || !container) return;
        viewMode.current = "manual";
        moveView(() => zoomBpmnAroundCenter(m, 1.25, container));
      },
      zoomOut: () => {
        const m = modelerRef.current;
        const container = containerRef.current;
        if (!m || !container) return;
        viewMode.current = "manual";
        moveView(() => zoomBpmnAroundCenter(m, 1 / 1.25, container));
      },
      fit: () => {
        const m = modelerRef.current;
        if (!m) return;
        viewMode.current = "fit";
        moveView(() => fitBpmnView(m, viewInset()));
      },
      focusElement: (id: string, cover?: Partial<BpmnViewInset>) => {
        const m = modelerRef.current;
        if (!m) return false;
        const el = (m.get("elementRegistry") as ElementRegistry).get(id);
        if (!el) return false;
        (m.get("selection") as Selection).select(el);
        viewMode.current = "manual";
        moveView(() => centerBpmnElement(m, el, { ...viewInset(), ...cover }));
        return true;
      },
      isEditing: () => {
        const m = modelerRef.current;
        if (!m) return false;
        try {
          return (
            (m.get("directEditing") as DirectEditing).isActive() ||
            Boolean((m.get("dragging") as Dragging).context())
          );
        } catch {
          return false;
        }
      },
      toggleFullscreen: () => callbacks.current.onToggleFullscreen?.(),
      documentationOf: (id: string) => {
        const m = modelerRef.current;
        if (!m) return null;
        try {
          const el = (m.get("elementRegistry") as ElementRegistry).get(id);
          return el ? documentationOf(el) : null;
        } catch {
          return null;
        }
      },
      lanes: () => {
        const m = modelerRef.current;
        if (!m) return [];
        try {
          return (m.get("elementRegistry") as ElementRegistry)
            .filter((el) => el.type === "bpmn:Lane")
            .sort((a, b) => (a.y ?? 0) - (b.y ?? 0))
            .map((el) => ({ id: el.id, name: el.businessObject?.name ?? "" }));
        } catch {
          return [];
        }
      },
      edgesOf: (id: string) => {
        const m = modelerRef.current;
        if (!m) return [];
        try {
          const el = (m.get("elementRegistry") as ElementRegistry).get(id);
          return el ? [...(el.incoming ?? []), ...(el.outgoing ?? [])].map((c) => c.id) : [];
        } catch {
          return [];
        }
      },
      refreshOps: () => {
        const m = modelerRef.current;
        if (!m || readOnlyRef.current) return;
        try {
          (m.get("eventBus") as EventBus).fire("gaik.context.changed");
          // An open context pad shows the tools of the mapping it was opened with.
          (m.get("contextPad") as { close: () => void }).close();
        } catch {
          /* tearing down */
        }
      },
    }),
    // The handle reads refs only.
    [],
  );

  const readOnlyRef = useRef(readOnly);
  useEffect(() => {
    readOnlyRef.current = readOnly;
  }, [readOnly]);

  // One canvas at a time: the modeler with the Workflow tab's tools, or the
  // viewer while the diagram is read-only. Both have the minimap.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let cancelled = false;
    let created: BpmnCanvas | null = null;
    const listeners: [string, (e: unknown) => void][] = [];

    (async () => {
      let m: BpmnCanvas;
      if (readOnly) {
        const { default: ViewerCtor } = await import("bpmn-js/lib/NavigatedViewer");
        if (cancelled) return;
        m = new ViewerCtor({
          container,
          additionalModules: [minimapModule],
          minimap: { open: true },
          ...BPMN_VIEWER_OPTIONS,
        } as ConstructorParameters<typeof ViewerCtor>[0]);
      } else {
        const { default: BpmnModelerCtor } = await import("bpmn-js/lib/Modeler");
        if (cancelled) return;
        m = new BpmnModelerCtor({
          container,
          additionalModules: [gaikEditorModule, minimapModule],
          // Always open: the minimap is part of the canvas, not a tool to switch on.
          minimap: { open: true },
          // Read when a tool is drawn, so the tools follow the UI language
          // and the server's latest mapping.
          gaikEditor: {
            get labels() {
              return labelsRef.current;
            },
            get ops() {
              return opsRef.current;
            },
          },
          ...BPMN_VIEWER_OPTIONS,
        } as ConstructorParameters<typeof BpmnModelerCtor>[0]);
      }
      created = m;
      modelerRef.current = m;

      const eventBus = m.get("eventBus") as EventBus;
      // diagram-js stops an event at the first listener that returns anything
      // but undefined, and a drag fires its prefixed event (create.cleanup,
      // shape.move.cleanup) with the event drag.cleanup was stopped in. A
      // listener here that returned setTimeout's id left every drag's preview
      // on the canvas: a box after "Lisää tehtävä" that no delete took away.
      // So these listeners only listen.
      const on = (event: string, cb: (e: unknown) => void) => {
        const listen = (e: unknown) => {
          cb(e);
        };
        eventBus.on(event, listen);
        listeners.push([event, listen]);
      };
      on("selection.changed", () => {
        if (!importing.current) callbacks.current.onSelectionChange?.(selectionFromModeler(m));
      });
      on("commandStack.changed", () => {
        if (importing.current) return;
        // A rename keeps the element selected; its new name goes to the panel.
        callbacks.current.onSelectionChange?.(selectionFromModeler(m));
      });
      on("directEditing.activate", () => callbacks.current.onDirectEditingChange?.(true));
      on("directEditing.deactivate", () => callbacks.current.onDirectEditingChange?.(false));
      // An edit in place or a drag can end without a command (Escape, no
      // change): whoever waited for it to end hears that it has.
      const settled = () =>
        window.setTimeout(() => {
          if (modelerRef.current === m) callbacks.current.onEditingEnd?.();
        }, 0);
      on("directEditing.deactivate", settled);
      on("drag.cleanup", settled);
      on("canvas.viewbox.changing", () => {
        if (!programmatic.current) viewMode.current = "manual";
      });
      on("canvas.viewbox.changed", () =>
        callbacks.current.onZoomChange?.((m.get("canvas") as Canvas).zoom()),
      );
      setModeler(m);
    })();

    return () => {
      cancelled = true;
      if (created) {
        if (importedOnce.current) {
          try {
            carried.current = {
              viewbox: (created.get("canvas") as Canvas).viewbox(),
              selected: selectionFromModeler(created)?.id ?? null,
            };
          } catch {
            /* tearing down */
          }
        }
        const eventBus = created.get("eventBus") as EventBus;
        for (const [event, cb] of listeners) {
          try {
            eventBus.off(event, cb);
          } catch {
            /* tearing down */
          }
        }
        created.destroy();
      }
      modelerRef.current = null;
      // The next canvas imports the diagram afresh.
      importedOnce.current = false;
      setReady(false);
      setModeler(null);
    };
  }, [readOnly]);

  // Import each new diagram into the same modeler. The first one opens on the
  // start view; a later one (after a save) keeps the view and the selection.
  useEffect(() => {
    if (!modeler) return;
    let cancelled = false;
    setError(false);

    (async () => {
      const canvas = modeler.get("canvas") as Canvas;
      // A canvas that took the other kind's place opens where that one stood.
      const carry = importedOnce.current ? null : carried.current;
      carried.current = null;
      const keepView = importedOnce.current ? canvas.viewbox() : (carry?.viewbox ?? null);
      const selected = importedOnce.current ? (selectionFromModeler(modeler)?.id ?? null) : (carry?.selected ?? null);
      importing.current = true;
      try {
        await modeler.importXML(stripTaskCodePrefixes(xml));
      } catch (err) {
        importing.current = false;
        console.error("[BpmnModeler] import failed:", err);
        if (!cancelled) setError(true);
        return;
      }
      importing.current = false;
      if (cancelled) return;
      importedOnce.current = true;
      if (keepView && keepView.width > 0) {
        moveView(() => canvas.viewbox(keepView));
      } else {
        viewMode.current = "start";
        moveView(() => applyBpmnStartView(modeler, viewInset()));
      }
      const registry = modeler.get("elementRegistry") as ElementRegistry;
      const again = selected ? registry.get(selected) : undefined;
      if (again) (modeler.get("selection") as Selection).select(again);
      else callbacks.current.onSelectionChange?.(null);
      setReady(true);
      callbacks.current.onImported?.();
    })();

    return () => {
      cancelled = true;
    };
    // Not the UI language: a language switch must not load the diagram again
    // under a name being typed.
  }, [modeler, xml, importKey]);

  // The palette is drawn once; a new UI language draws its tools again. The
  // context pad reads its labels each time it opens.
  const { addTask, connect, derived } = editorLabels;
  useEffect(() => {
    if (!modeler) return;
    try {
      const eventBus = modeler.get("eventBus") as EventBus;
      eventBus.fire("i18n.changed");
      eventBus.fire("gaik.context.changed");
    } catch {
      /* tearing down */
    }
  }, [modeler, addTask, connect, derived]);

  // The minimap is named for a screen reader, in the UI language.
  useEffect(() => {
    const map = modeler && containerRef.current?.querySelector<HTMLElement>(".djs-minimap");
    if (!map || !minimapLabel) return;
    map.setAttribute("role", "group");
    map.setAttribute("aria-label", minimapLabel);
    map.setAttribute("title", minimapLabel);
  }, [modeler, minimapLabel]);

  // A new size re-fits the start view and the fit; a view the user picked stays.
  useEffect(() => {
    if (!ready) return;
    const container = containerRef.current;
    if (!container) return;
    const ro = new ResizeObserver(() => {
      const m = modelerRef.current;
      if (m) moveView(() => reapplyBpmnView(m, viewMode.current, viewInset()));
    });
    ro.observe(container);
    return () => ro.disconnect();
  }, [ready]);

  return (
    <>
      {error && (
        <p className="absolute inset-x-3 top-3 z-10 text-sm text-danger-text" role="alert">
          {loadErrorLabel}
        </p>
      )}
      <div
        ref={containerRef}
        // isolate: bpmn-js's context pad (z-index 100) stays under the panels drawn over the canvas.
        // bpmn-editable is the Workflow tab's look (bpmn-js's own lane names), read-only or not.
        className={`bpmn-viewer-themed bpmn-editable isolate h-full overflow-hidden ${className}`}
        role="application"
        aria-label={ariaLabel}
        aria-busy={!ready}
        data-read-only={readOnly}
      />
    </>
  );
});
