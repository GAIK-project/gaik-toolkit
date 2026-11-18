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
import {
  bpmnChangeKind,
  bpmnSaveProblems,
  bpmnSemantics,
  isRenamableBpmnElement,
  stripTaskCodePrefixes,
  type BpmnSemantics,
  type ModdleElement,
} from "@/lib/bpmn-edit-state";
import { gaikEditorModule, type BpmnEditorLabels } from "@/lib/bpmn-editor-module";
import "bpmn-js/dist/assets/diagram-js.css";
import "bpmn-js/dist/assets/bpmn-js.css";
import "bpmn-js/dist/assets/bpmn-font/css/bpmn-embedded.css";

type EventBus = {
  on: (event: string, cb: (e: unknown) => void) => void;
  off: (event: string, cb: (e: unknown) => void) => void;
  fire: (event: string) => void;
};

type Modeling = {
  updateProperties: (element: unknown, props: Record<string, unknown>) => void;
};

type DiagramElement = {
  id: string;
  type: string;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  labelTarget?: DiagramElement;
  businessObject?: { id?: string; name?: string; $type?: string };
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

type ElementRegistry = { get: (id: string) => DiagramElement | undefined };

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
} | null;

/** Unsaved edits on the canvas, measured against the diagram last imported. */
export type BpmnEditState = {
  kind: "none" | "rename" | "structure";
  problems: ReturnType<typeof bpmnSaveProblems>;
};

export type BpmnModelerHandle = {
  saveXml: () => Promise<string>;
  zoomIn: () => void;
  zoomOut: () => void;
  fit: () => void;
  updateSelectedName: (name: string) => void;
  /**
   * Select an element and bring it to the middle of the view; false if it is
   * not on the canvas. `cover` is what a panel over the canvas hides, in screen px.
   */
  focusElement: (id: string, cover?: Partial<BpmnViewInset>) => boolean;
  /** Counts the edits since the last import: a save compares it to see whether more came in. */
  revision: () => number;
  /** What the canvas holds now, as the blueprint sync reads it. */
  semantics: () => BpmnSemantics;
  /** What the server has now, for diagrams kept on the canvas after a save or restored from a draft. */
  setBase: (base: BpmnSemantics) => void;
  /**
   * The user is in the middle of an edit that is no command yet: typing a
   * label in place, or dragging. An import now would throw it away, and the
   * revision does not count it.
   */
  isEditing: () => boolean;
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
    return { id, type: type.replace(/^bpmn:/, ""), name: bo?.name || "" };
  } catch {
    return null;
  }
}

/**
 * The Workflow tab's BPMN diagram. One bpmn-js modeler lives as long as the
 * component; a new `xml` is imported into it, keeping the user's view and
 * selection, so a save does not throw the diagram back to its start view.
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
    className?: string;
    onSelectionChange?: (info: BpmnSelectionInfo) => void;
    onEditStateChange?: (state: BpmnEditState) => void;
    onZoomChange?: (zoom: number) => void;
    /** After each import, when the diagram is on the canvas. */
    onImported?: () => void;
    /** After an edit in place or a drag has ended, with or without a change (see `isEditing`). */
    onEditingEnd?: () => void;
    /** A new value imports `xml` again even when the text is the same (after a save). */
    importKey?: number;
    /** The diagram can be looked at, moved and its elements picked, but not changed. */
    readOnly?: boolean;
  }
>(function BpmnModeler(
  {
    xml,
    ariaLabel,
    loadErrorLabel,
    editorLabels,
    className = "",
    onSelectionChange,
    onEditStateChange,
    onZoomChange,
    onImported,
    onEditingEnd,
    importKey = 0,
    readOnly = false,
  },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const modelerRef = useRef<BpmnCanvas | null>(null);
  const callbacks = useRef({ onSelectionChange, onEditStateChange, onZoomChange, onImported, onEditingEnd });
  callbacks.current = { onSelectionChange, onEditStateChange, onZoomChange, onImported, onEditingEnd };
  const labelsRef = useRef(editorLabels);
  labelsRef.current = editorLabels;
  const [modeler, setModeler] = useState<BpmnCanvas | null>(null);
  const [error, setError] = useState(false);
  const [ready, setReady] = useState(false);

  const viewMode = useRef<BpmnViewMode>("start");
  // True while this component moves the view itself; any other change of the
  // view (wheel, drag, keys) is the user's, and a resize then keeps it.
  const programmatic = useRef(false);
  const base = useRef<BpmnSemantics | null>(null);
  const revisionRef = useRef(0);
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

  function currentSemantics(m: BpmnCanvas): BpmnSemantics {
    return bpmnSemantics(m.getDefinitions() as unknown as ModdleElement);
  }

  function reportEditState(m: BpmnCanvas) {
    if (!base.current) return;
    const now = currentSemantics(m);
    callbacks.current.onEditStateChange?.({
      kind: bpmnChangeKind(base.current, now),
      problems: bpmnSaveProblems(now),
    });
  }

  useImperativeHandle(
    ref,
    () => ({
      saveXml: async () => {
        const m = modelerRef.current;
        if (!m) throw new Error("modeler not ready");
        const { xml: saved } = await m.saveXML({ format: true });
        if (!saved) throw new Error("empty BPMN XML");
        return saved;
      },
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
      updateSelectedName: (name: string) => {
        const m = modelerRef.current;
        if (!m) return;
        try {
          const selected = (m.get("selection") as Selection).get?.() ?? [];
          const el = selected[0]?.labelTarget ?? selected[0];
          if (!el) return;
          (m.get("modeling") as Modeling).updateProperties(el, { name });
        } catch {
          /* ignore */
        }
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
      revision: () => revisionRef.current,
      semantics: () => {
        const m = modelerRef.current;
        return m ? currentSemantics(m) : bpmnSemantics(null);
      },
      setBase: (next: BpmnSemantics) => {
        base.current = next;
        const m = modelerRef.current;
        if (m) reportEditState(m);
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
    }),
    // The handle reads refs only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  // One canvas at a time: the modeler with the Workflow tab's tools, or the
  // viewer while the diagram is read-only.
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
        m = new ViewerCtor({ container, ...BPMN_VIEWER_OPTIONS } as ConstructorParameters<typeof ViewerCtor>[0]);
      } else {
        const { default: BpmnModelerCtor } = await import("bpmn-js/lib/Modeler");
        if (cancelled) return;
        m = new BpmnModelerCtor({
          container,
          additionalModules: [gaikEditorModule],
          // Read when a tool is drawn, so the tools follow the UI language.
          gaikEditor: {
            get labels() {
              return labelsRef.current;
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
        revisionRef.current += 1;
        reportEditState(m);
        // A rename keeps the element selected; its new name goes to the panel.
        callbacks.current.onSelectionChange?.(selectionFromModeler(m));
      });
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
    // reportEditState reads refs only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      revisionRef.current = 0;
      base.current = currentSemantics(modeler);
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
      reportEditState(modeler);
      setReady(true);
      callbacks.current.onImported?.();
    })();

    return () => {
      cancelled = true;
    };
    // Not the UI language: a language switch must not load the diagram again
    // over unsaved edits. moveView and reportEditState read refs only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modeler, xml, importKey]);

  // The palette is drawn once; a new UI language draws its tools again. The
  // context pad reads its labels each time it opens.
  const { addTask, connect, rename, remove } = editorLabels;
  useEffect(() => {
    if (!modeler) return;
    try {
      (modeler.get("eventBus") as EventBus).fire("i18n.changed");
    } catch {
      /* tearing down */
    }
  }, [modeler, addTask, connect, rename, remove]);

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
    // moveView reads refs only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
        className={`bpmn-viewer-themed bpmn-editable isolate h-full overflow-hidden [&_.bjs-powered-by]:hidden ${className}`}
        role="application"
        aria-label={ariaLabel}
        aria-busy={!ready}
        data-read-only={readOnly}
      />
    </>
  );
});
