/**
 * The Workflow tab's editing tools, as a bpmn-js module.
 *
 * The canvas does not save a diagram: each edit is sent at once as an
 * operation on the blueprint (lib/bpmn-canvas-ops), and the panel then draws
 * the server's diagram again. So the canvas offers only the edits an
 * operation can make, and only on the steps (`workflow.steps`) the server's
 * mapping names; what the blueprint draws from elsewhere (start and end,
 * gateways, lanes, data) has no tools and says why when the pointer is on it.
 *
 * - Palette: "Add step" (after the last step) and the connect tool.
 * - A step's context pad: rename, append a step, move earlier and later,
 *   connect and delete. A flow between two steps: delete.
 * - A rename typed in place, a line drawn with the connect tool and the
 *   Delete key are bpmn-js commands: once one has run, it is read here and
 *   sent as its operation (or, when it means nothing for the blueprint, the
 *   panel puts the server's diagram back). Dragging shapes changes no
 *   blueprint: their new places are handed over as a layout.
 *
 * Labels and the operations come in through the modeler's `gaikEditor`
 * config, read each time they are needed.
 */
import type DiagramEventBus from "diagram-js/lib/core/EventBus";
import RuleProvider from "diagram-js/lib/features/rules/RuleProvider";
import type { BlueprintOperation } from "@/lib/blueprint-ops";
import {
  isOperationElement,
  opForAddStep,
  opForAppend,
  opForConnection,
  opForDelete,
  opForLabelUpdate,
  opsForMove,
  stepIdOf,
  type BpmnMapping,
  type CanvasElement,
  type StepRef,
} from "@/lib/bpmn-canvas-ops";

export type BpmnEditorLabels = {
  addTask: string;
  connect: string;
  rename: string;
  remove: string;
  append: string;
  moveEarlier: string;
  moveLater: string;
  connectFrom: string;
  /** Why an element the blueprint draws from elsewhere has no tools. */
  derived: string;
  /** The name a step added from the canvas starts with. */
  newStepName: string;
};

/** Where dragged shapes and edges now are, as `PUT /bpmn/layout` takes it. */
export type BpmnLayoutChange = {
  shapes: Record<string, { x: number; y: number }>;
  edges: Record<string, [number, number][]>;
};

export type BpmnEditorOps = {
  /** The mapping and steps the canvas stands on; null while there are none to edit with. */
  context: () => { mapping: BpmnMapping; steps: StepRef[] } | null;
  onOperation: (ops: BlueprintOperation[]) => void;
  /** The canvas changed in a way no operation describes: the server's diagram goes back on it. */
  onRevert: () => void;
  onLayout: (layout: BpmnLayoutChange) => void;
};

type Config = { labels: BpmnEditorLabels; ops: BpmnEditorOps | null };

type Shape = {
  id: string;
  type: string;
  x: number;
  y: number;
  width: number;
  height: number;
  labelTarget?: Shape;
  incoming?: Connection[];
  outgoing?: Connection[];
  waypoints?: undefined;
};
type Connection = {
  id: string;
  type: string;
  source: Shape;
  target: Shape;
  waypoints: { x: number; y: number }[];
  labelTarget?: undefined;
};
type Element = Shape | Connection;
type Entry = Record<string, unknown>;
type Entries = Record<string, Entry>;

type Palette = { registerProvider: (priority: number, provider: unknown) => void };
type ContextPad = { registerProvider: (priority: number, provider: unknown) => void };
type DirectEditing = { activate: (element: Element) => boolean };
type ElementRegistry = {
  getAll: () => Element[];
  getGraphics: (element: Element) => SVGElement | undefined;
};
type Keyboard = {
  isCmd: (event: KeyboardEvent) => boolean;
  isKey: (keys: string | string[], event: KeyboardEvent) => boolean;
};

/** The element a label belongs to: a label's edits are its owner's. */
const owner = (el: Element): Element => el.labelTarget ?? el;

const isConnection = (el: Element): el is Connection => Array.isArray(el.waypoints);

/** What the operation helpers read of an element. */
function canvasElement(el: Element): CanvasElement {
  const target = owner(el);
  return isConnection(target)
    ? { id: target.id, type: target.type, source: target.source?.id, target: target.target?.id }
    : { id: target.id, type: target.type };
}

/** Shapes the layout does not keep: lanes and pools span the drawing, and the root is no shape. */
const FIXED = new Set(["bpmn:Lane", "bpmn:Participant", "bpmn:Process", "bpmn:Collaboration"]);

/** The ids `PUT /bpmn/layout` takes (`_ID_RE` in wizard_api's bpmn_layout). */
const LAYOUT_ID = /^[A-Za-z0-9_.-]{1,100}$/;

function icon(path: string): string {
  return (
    "data:image/svg+xml;utf8," +
    encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#22242a" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${path}</svg>`,
    )
  );
}

// Lucide icons (ISC), the same set as components/icons.tsx.
const PENCIL = icon(
  '<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/><path d="m15 5 4 4"/>',
);
const PLUS = icon('<path d="M5 12h14"/><path d="M12 5v14"/>');
const ARROW_LEFT = icon('<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>');
const ARROW_RIGHT = icon('<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>');

/** A context pad entry that is shown but does nothing (the first step cannot move earlier). */
const disabled = (title: string, imageUrl: string): Entry => ({
  group: "edit",
  html: '<div class="entry gaik-pad-disabled" aria-disabled="true"></div>',
  imageUrl,
  title,
  action: {},
});

/** "Add step" and the connect tool, nothing else. */
class GaikPalette {
  static $inject = ["palette", "config.gaikEditor"];
  constructor(
    palette: Palette,
    private config: Config,
  ) {
    // After bpmn-js's own provider (priority 1000), so its entries are there to pick from.
    palette.registerProvider(500, this);
  }
  getPaletteEntries() {
    const { labels, ops } = this.config;
    return (entries: Entries): Entries => {
      const out: Entries = {};
      if (!ops) return out;
      out["gaik-add-step"] = {
        group: "activity",
        className: "bpmn-icon-task",
        title: labels.addTask,
        action: {
          click: () => {
            const ctx = ops.context();
            if (ctx) ops.onOperation([opForAddStep(labels.newStepName, ctx.steps)]);
          },
        },
      };
      if (entries["global-connect-tool"]) {
        out["global-connect-tool"] = { ...entries["global-connect-tool"], title: labels.connect };
      }
      return out;
    };
  }
}

/** A step: rename, append, move, connect, delete. A flow between steps: delete. Nothing else. */
class GaikContextPad {
  static $inject = ["contextPad", "directEditing", "config.gaikEditor"];
  constructor(
    contextPad: ContextPad,
    private directEditing: DirectEditing,
    private config: Config,
  ) {
    contextPad.registerProvider(500, this);
  }
  getContextPadEntries(element: Element) {
    const { labels, ops } = this.config;
    return (entries: Entries): Entries => {
      const ctx = ops?.context();
      if (!ops || !ctx || element !== owner(element)) return {};
      const { mapping, steps } = ctx;
      if (isConnection(element)) {
        const op = opForDelete(canvasElement(element), mapping, steps);
        return op
          ? {
              delete: {
                group: "edit",
                className: "bpmn-icon-trash",
                title: labels.remove,
                action: { click: () => ops.onOperation([op]) },
              },
            }
          : {};
      }
      if (!stepIdOf(element.id, mapping, steps)) return {};
      const out: Entries = {
        rename: {
          group: "edit",
          imageUrl: PENCIL,
          title: labels.rename,
          action: { click: () => this.directEditing.activate(element) },
        },
      };
      const append = opForAppend(element.id, labels.newStepName, mapping, steps);
      if (append) {
        out.append = {
          group: "edit",
          imageUrl: PLUS,
          title: labels.append,
          action: { click: () => ops.onOperation([append]) },
        };
      }
      const earlier = opsForMove(element.id, "earlier", mapping, steps);
      out["move-earlier"] = earlier
        ? { group: "edit", imageUrl: ARROW_LEFT, title: labels.moveEarlier, action: { click: () => ops.onOperation(earlier) } }
        : disabled(labels.moveEarlier, ARROW_LEFT);
      const later = opsForMove(element.id, "later", mapping, steps);
      out["move-later"] = later
        ? { group: "edit", imageUrl: ARROW_RIGHT, title: labels.moveLater, action: { click: () => ops.onOperation(later) } }
        : disabled(labels.moveLater, ARROW_RIGHT);
      if (entries.connect) out.connect = { ...entries.connect, group: "connect", title: labels.connectFrom };
      const remove = opForDelete(canvasElement(element), mapping, steps);
      if (remove) {
        out.delete = {
          group: "edit",
          className: "bpmn-icon-trash",
          title: labels.remove,
          action: { click: () => ops.onOperation([remove]) },
        };
      }
      return out;
    };
  }
  getMultiElementContextPadEntries() {
    // One operation at a time: several elements picked together get no tools.
    return (): Entries => ({});
  }
}

/**
 * What the keyboard and the mouse may still do: Delete removes one step or
 * one flow between steps; lines start and end at steps; nothing is created,
 * resized, copied or reconnected (no operation keeps that); lanes and pools
 * stay where the drawing puts them.
 */
class GaikRules extends RuleProvider {
  static $inject = ["eventBus", "config.gaikEditor"];
  constructor(
    eventBus: DiagramEventBus,
    private config: Config,
  ) {
    super(eventBus);
  }
  init() {
    const ctx = () => this.config.ops?.context() ?? null;
    const isStep = (el?: Element) => {
      const c = ctx();
      return Boolean(el && c && stepIdOf(owner(el).id, c.mapping, c.steps));
    };
    this.addRule("elements.delete", 2000, (context: { elements: Element[] }) => {
      const c = ctx();
      if (!c || context.elements.length !== 1) return false;
      const [el] = context.elements;
      return el === owner(el) && isOperationElement(canvasElement(el), c.mapping, c.steps) ? [el] : false;
    });
    this.addRule("shape.resize", 2000, () => false);
    this.addRule(["shape.create", "elements.create", "elements.paste", "element.copy", "shape.attach"], 2000, () => false);
    this.addRule("connection.start", 2000, (context: { source?: Element }) => (isStep(context.source) ? undefined : false));
    this.addRule("connection.create", 2000, (context: { source?: Element; target?: Element }) =>
      isStep(context.source) && isStep(context.target) && context.source !== context.target ? undefined : false,
    );
    this.addRule("connection.reconnect", 2000, () => false);
    this.addRule("elements.move", 2000, (context: { shapes?: Element[] }) =>
      (context.shapes ?? []).some((s) => FIXED.has(s.type)) ? false : undefined,
    );
  }
}

/** The commands a move may run inside it and still be only a move. */
const MOVE_COMMANDS = new Set([
  "elements.move",
  "shape.move",
  "connection.move",
  "connection.layout",
  "connection.updateWaypoints",
  "lane.updateRefs",
  "element.updateProperties",
  "element.updateModdleProperties",
  "label.move",
]);
/** A top-level command that is a layout change when only MOVE_COMMANDS run inside it. */
const MOVE_ROOTS = new Set(["elements.move", "shape.move", "connection.updateWaypoints", "connection.move"]);

/**
 * Reads each finished bpmn-js command (the outermost one, with what ran inside
 * it) and hands it on as an operation, a layout change or a revert. Local
 * undo and redo (Ctrl+Z, Ctrl+Y) are off: the blueprint's own Undo is the
 * way back, and a local undo would leave the canvas apart from the server.
 */
class GaikOperations {
  static $inject = ["eventBus", "config.gaikEditor", "elementRegistry", "keyboard"];
  private depth = 0;
  private top: { command: string; context: Record<string, unknown> } | null = null;
  private nested = new Set<string>();
  private shapes = new Set<Shape>();
  private edges = new Set<Connection>();

  constructor(
    eventBus: DiagramEventBus,
    private config: Config,
    private registry: ElementRegistry,
    keyboard: Keyboard,
  ) {
    eventBus.on("commandStack.preExecute", (e: { command: string; context: Record<string, unknown> }) => {
      this.depth += 1;
      if (this.depth === 1) this.top = { command: e.command, context: e.context };
      else this.nested.add(e.command);
      if (e.command === "shape.move") this.shapes.add(e.context.shape as Shape);
      if (["connection.layout", "connection.updateWaypoints", "connection.move"].includes(e.command)) {
        this.edges.add(e.context.connection as Connection);
      }
    });
    eventBus.on("commandStack.postExecuted", () => {
      this.depth = Math.max(0, this.depth - 1);
    });
    eventBus.on("commandStack.changed", (e: { trigger?: string }) => {
      const top = this.top;
      const nested = this.nested;
      const shapes = this.shapes;
      const edges = this.edges;
      this.reset();
      if (e.trigger !== "execute" || !top) return;
      // Out of bpmn-js's command stack before anything else happens.
      window.setTimeout(() => this.handle(top, nested, shapes, edges), 0);
    });
    eventBus.on("diagram.clear", () => this.reset());

    eventBus.on("keyboard.keydown", 2000, (e: { keyEvent: KeyboardEvent }) => {
      const event = e.keyEvent;
      if (keyboard.isCmd(event) && keyboard.isKey(["z", "Z", "y", "Y"], event)) return true;
      return undefined;
    });

    // Double-click and the E key rename in place: a step only.
    eventBus.on("directEditing.activate.allowed", 2000, (e: { element: Element }) => {
      const c = this.config.ops?.context();
      return c && stepIdOf(owner(e.element).id, c.mapping, c.steps) ? undefined : false;
    });

    // Why an element has no tools, while the pointer is on it.
    eventBus.on("import.done", () => this.markDerived());
    eventBus.on("gaik.context.changed", () => this.markDerived());
  }

  private reset() {
    this.depth = 0;
    this.top = null;
    this.nested = new Set();
    this.shapes = new Set();
    this.edges = new Set();
  }

  private handle(
    top: { command: string; context: Record<string, unknown> },
    nested: Set<string>,
    shapes: Set<Shape>,
    edges: Set<Connection>,
  ) {
    const ops = this.config.ops;
    if (!ops) return;
    const ctx = ops.context();
    const send = (op: BlueprintOperation | null) => (op ? ops.onOperation([op]) : ops.onRevert());
    switch (top.command) {
      case "element.updateLabel": {
        const element = top.context.element as Element | undefined;
        if (!ctx || !element) return ops.onRevert();
        return send(opForLabelUpdate(owner(element).id, top.context.newLabel as string, ctx.mapping, ctx.steps));
      }
      case "connection.create": {
        const source = top.context.source as Element | undefined;
        const target = top.context.target as Element | undefined;
        if (!ctx || !source || !target) return ops.onRevert();
        return send(opForConnection(source.id, target.id, ctx.mapping, ctx.steps));
      }
      case "elements.delete": {
        const elements = (top.context.elements as Element[] | undefined) ?? [];
        if (!ctx || elements.length !== 1) return ops.onRevert();
        return send(opForDelete(canvasElement(elements[0]), ctx.mapping, ctx.steps));
      }
    }
    if (MOVE_ROOTS.has(top.command) && [...nested].every((c) => MOVE_COMMANDS.has(c))) {
      const layout: BpmnLayoutChange = { shapes: {}, edges: {} };
      for (const shape of shapes) {
        if (shape.labelTarget || FIXED.has(shape.type) || !LAYOUT_ID.test(shape.id)) continue;
        layout.shapes[shape.id] = { x: Math.round(shape.x), y: Math.round(shape.y) };
      }
      for (const edge of edges) {
        if (!LAYOUT_ID.test(edge.id) || edge.waypoints.length < 2 || edge.waypoints.length > 100) continue;
        layout.edges[edge.id] = edge.waypoints.map((p) => [Math.round(p.x), Math.round(p.y)]);
      }
      if (Object.keys(layout.shapes).length || Object.keys(layout.edges).length) ops.onLayout(layout);
      return;
    }
    // A change no operation describes (a shape dropped onto a flow, which
    // bpmn-js splits): the server's diagram goes back on the canvas.
    ops.onRevert();
  }

  private markDerived() {
    const ctx = this.config.ops?.context() ?? null;
    const text = this.config.labels.derived;
    for (const el of this.registry.getAll()) {
      const gfx = this.registry.getGraphics(el);
      if (!gfx) continue;
      gfx.querySelector(":scope > title.gaik-derived")?.remove();
      gfx.removeAttribute("data-gaik-derived");
      if (!ctx || el.labelTarget || FIXED.has(el.type) || !el.type.startsWith("bpmn:")) continue;
      if (isOperationElement(canvasElement(el), ctx.mapping, ctx.steps)) continue;
      const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      title.setAttribute("class", "gaik-derived");
      title.textContent = text;
      gfx.prepend(title);
      gfx.setAttribute("data-gaik-derived", "true");
    }
  }
}

export const gaikEditorModule = {
  __init__: ["gaikPalette", "gaikContextPad", "gaikRules", "gaikOperations"],
  gaikPalette: ["type", GaikPalette],
  gaikContextPad: ["type", GaikContextPad],
  gaikRules: ["type", GaikRules],
  gaikOperations: ["type", GaikOperations],
};
