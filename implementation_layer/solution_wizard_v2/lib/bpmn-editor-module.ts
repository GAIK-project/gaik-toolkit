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
 * - A step's context pad: rename, change its type, append a step, move
 *   earlier and later, connect and delete. A flow between two steps: delete.
 * - "Change type" opens the `gaik-step-type` menu: user task, AI step and
 *   human review, each a `set_step_type`. bpmn-js's own replace menu stays
 *   off: a user task and a review both draw as `bpmn:UserTask`, so changing
 *   the drawn element says nothing of the step's type.
 * - A rename typed in place, a line drawn with the connect tool and the
 *   Delete key are bpmn-js commands: once one has run, it is read here and
 *   sent as its operation (or, when it means nothing for the blueprint, the
 *   panel puts the server's diagram back). Dragging shapes within their
 *   lane and bending flows changes no blueprint: their new places are handed
 *   over as a layout (`onLayout`), which the panel keeps with
 *   `PUT /bpmn/layout`. A step dragged into another lane is put in that lane
 *   (`set_step_lane`, through `onStepLane`); anything else dragged into
 *   another lane is refused.
 * - Lanes: the palette's "Add lane" (`add_lane`), and a lane's context pad:
 *   rename it in place (`rename_lane`) and remove it (`remove_lane`).
 * - Business decisions: a step's "Add decision after" and a decision
 *   gateway's Edit open the branch dialog (`onDecision`, in the panel); a
 *   decision gateway's Remove (and the Delete key) is `remove_decision`. A
 *   gateway the generator draws by itself (the approval after a review) has
 *   no tools of its own: it has a path's Edit and Remove only when its "No"
 *   draws a rework path (below). A decision step (a `workflow.steps` entry
 *   drawn as a gateway) keeps the step tools.
 * - Rework and rejection paths: a step's "Add rework path" and a path's Edit
 *   open the path dialog (`onRework`, in the panel); a path's Remove (and the
 *   Delete key) is `remove_rework_path`. A path's elements are its gateway,
 *   its end event, and the approval gateway of a review whose "No" is the
 *   path's loop back. On that approval gateway the Delete key does nothing
 *   (`opForDeleteKey`): it stands for the review, and only its pad's Remove
 *   removes the path.
 * - Data objects (drawn only with "Show data" on): a data object's pad renames
 *   it in place (`rename_data_object`, an emptied name clears its own) and
 *   starts a line to a step. The connect tool between a data object and a
 *   step is `link_data`: from the data object the step uses it (input), from
 *   the step it makes it (output). Deleting such an association is
 *   `unlink_data` (refused for the only step that makes a generated data
 *   object: a link's removal never deletes it). Only a task takes a data
 *   link, not a decision step's gateway. A data object itself has no Delete; data stores (drawn
 *   from the integration targets) have no tools.
 *
 * Labels and the operations come in through the modeler's `gaikEditor`
 * config, read each time they are needed.
 */
import type DiagramEventBus from "diagram-js/lib/core/EventBus";
import RuleProvider from "diagram-js/lib/features/rules/RuleProvider";
import type { BlueprintOperation, StepType } from "@/lib/blueprint-ops";
import { STEP_OP_TYPES } from "@/lib/step-panel-model";
import {
  dataObjectOf,
  decisionOf,
  holdsData,
  exceptionOf,
  isDecisionStep,
  stepHasDecision,
  isOperationElement,
  opForAddStep,
  opForAppend,
  opForConnection,
  opForDataObjectRename,
  opForDelete,
  opForDeleteKey,
  opForLabelUpdate,
  opForLaneRename,
  opForStepLane,
  opsForMove,
  laneIdOf,
  stepIdOf,
  type BpmnMapping,
  type CanvasElement,
  type DecisionRef,
  type ExceptionRef,
  type StepRef,
} from "@/lib/bpmn-canvas-ops";

export type BpmnEditorLabels = {
  addTask: string;
  connect: string;
  rename: string;
  /** A step's context pad, and the title of the menu it opens. */
  changeType: string;
  /** The menu's entries, in the words the step list uses. */
  stepTypes: Record<StepType, string>;
  remove: string;
  append: string;
  moveEarlier: string;
  moveLater: string;
  connectFrom: string;
  /** Why an element the blueprint draws from elsewhere has no tools. */
  derived: string;
  /** The name a step added from the canvas starts with. */
  newStepName: string;
  addLane: string;
  /** The name a lane added from the palette starts with. */
  newLaneName: string;
  renameLane: string;
  removeLane: string;
  /** A step's pad: a business decision after it; a decision gateway's pad: edit and remove it. */
  addDecision: string;
  editDecision: string;
  removeDecision: string;
  /** A step's pad: a rework or rejection path on it; a path's pad: edit and remove it. */
  addRework: string;
  editRework: string;
  removeRework: string;
  /** A data object's pad: rename it in place, and draw a line from it to a step. */
  renameDataObject: string;
  connectData: string;
};

/** What the branch dialog opens for: a new decision after a step, or a decision to edit. */
export type BpmnDecisionRequest = { after: string } | { decision: DecisionRef };

/** What the path dialog opens for: a new path on a step, or a path to edit. */
export type BpmnReworkRequest = { attachedTo: string } | { exception: ExceptionRef };

/**
 * A step put in another lane: the operation, and the drawn places that no
 * longer fit (the step's and its flows'), which the panel drops from the
 * layout so the step is drawn in its new lane.
 */
export type BpmnStepLaneChange = {
  op: BlueprintOperation;
  shapes: string[];
  edges: string[];
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
  /** A step dragged into another lane. */
  onStepLane: (change: BpmnStepLaneChange) => void;
  /** Opens the branch dialog: it sends the decision through `onOperation`'s gate. */
  onDecision: (request: BpmnDecisionRequest) => void;
  /** Opens the path dialog: it sends the path through `onOperation`'s gate. */
  onRework: (request: BpmnReworkRequest) => void;
  /** The type a step has now, as the step panel shows it; null when unknown. */
  stepType: (stepId: string) => StepType | null;
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
  parent?: Element;
  /** The BPMN element; a lane's lists the flow nodes in it (`flowNodeRef`). */
  businessObject?: { id?: string; name?: string; flowNodeRef?: unknown[] };
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
  parent?: Element;
};
type Element = Shape | Connection;
type Entry = Record<string, unknown>;
type Entries = Record<string, Entry>;

type Palette = { registerProvider: (priority: number, provider: unknown) => void };
type ContextPad = {
  registerProvider: (priority: number, provider: unknown) => void;
  /** diagram-js's own placement of the pad, in px within the canvas's container. */
  _getPosition?: (target: unknown) => Record<string, number>;
};
type Canvas = { getContainer: () => HTMLElement };
type PopupMenu = {
  registerProvider: (id: string, provider: unknown) => void;
  open: (target: Element, providerId: string, position: { x: number; y: number }, options?: unknown) => void;
  close: () => void;
};
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
// Lucide "split": a decision's branches.
const SPLIT = icon(
  '<path d="M16 3h5v5"/><path d="M8 3H3v5"/><path d="M12 22v-8.3a4 4 0 0 0-1.172-2.872L3 3"/><path d="m15 9 6-6"/>',
);
// Lucide "undo-2": a path back to an earlier step.
const UNDO = icon('<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"/>');
const TYPE_ICONS: Record<StepType, string> = {
  // arrowRightLeft, brain and userCheck: the step list's icons for the three types.
  user_task: icon('<path d="m16 3 4 4-4 4"/><path d="M20 7H4"/><path d="m8 21-4-4 4-4"/><path d="M4 17h16"/>'),
  automated_task: icon(
    '<path d="M12 18V5"/><path d="M15 13a4.17 4.17 0 0 1-3-4 4.17 4.17 0 0 1-3 4"/><path d="M17.598 6.5A3 3 0 1 0 12 5a3 3 0 1 0-5.598 1.5"/><path d="M17.997 5.125a4 4 0 0 1 2.526 5.77"/><path d="M18 18a4 4 0 0 0 2-7.464"/><path d="M19.967 17.483A4 4 0 1 1 12 18a4 4 0 1 1-7.967-.517"/><path d="M6 18a4 4 0 0 1-2-7.464"/><path d="M6.003 5.125a4 4 0 0 0-2.526 5.77"/>',
  ),
  human_review: icon('<path d="m16 11 2 2 4-4"/><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'),
};

/** Room for a lane's two pad entries, inside the lane's right edge. */
const LANE_PAD_WIDTH = 90;
/** The canvas's "Show data" and zoom buttons cover its top right this far down. */
const LANE_PAD_TOP = 56;

/** The step type menu's id with diagram-js's popup menu. */
export const STEP_TYPE_MENU = "gaik-step-type";

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
      out["gaik-add-lane"] = {
        group: "activity",
        className: "bpmn-icon-lane-insert-below",
        title: labels.addLane,
        action: {
          click: () => {
            if (ops.context()) ops.onOperation([{ op: "add_lane", name: labels.newLaneName }]);
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

/** A step: rename, change type, append, move, connect, delete. A flow between steps: delete. Nothing else. */
class GaikContextPad {
  static $inject = ["contextPad", "directEditing", "popupMenu", "elementRegistry", "config.gaikEditor", "canvas"];
  constructor(
    contextPad: ContextPad,
    private directEditing: DirectEditing,
    private popupMenu: PopupMenu,
    private registry: ElementRegistry,
    private config: Config,
    canvas: Canvas,
  ) {
    contextPad.registerProvider(500, this);
    // A lane spans the whole drawing, so the pad at its top right corner is
    // often out of view: a lane's pad sits at the top right of the part of
    // the lane that is on screen.
    const place = contextPad._getPosition?.bind(contextPad);
    if (place) {
      contextPad._getPosition = (target: unknown) => {
        const lane = target as Element;
        const gfx = !Array.isArray(target) && lane?.type === "bpmn:Lane" ? registry.getGraphics(lane) : undefined;
        if (!gfx) return place(target);
        const box = canvas.getContainer().getBoundingClientRect();
        const r = gfx.getBoundingClientRect();
        const right = Math.min(r.right, box.right) - box.left;
        // Below the canvas's own buttons at its top right, and within the lane.
        const top = Math.min(Math.max(r.top - box.top, LANE_PAD_TOP), r.bottom - box.top - 40);
        return { left: Math.max(0, right - LANE_PAD_WIDTH), top: top + 6 };
      };
    }
  }

  /** The type menu, just under the step. */
  private openTypeMenu(element: Element, event: MouseEvent) {
    const rect = this.registry.getGraphics(element)?.getBoundingClientRect();
    const position = rect ? { x: rect.left, y: rect.bottom + 8 } : { x: event.clientX, y: event.clientY };
    this.popupMenu.open(element, STEP_TYPE_MENU, position, { title: this.config.labels.changeType, width: 240 });
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
      if (element.type === "bpmn:Lane") {
        const laneId = laneIdOf(element.id, mapping);
        if (!laneId) return {};
        return {
          "gaik-lane-rename": {
            group: "edit",
            imageUrl: PENCIL,
            title: labels.renameLane,
            action: { click: () => this.directEditing.activate(element) },
          },
          "gaik-lane-remove": {
            group: "edit",
            className: "bpmn-icon-trash",
            title: labels.removeLane,
            action: { click: () => ops.onOperation([{ op: "remove_lane", lane_id: laneId }]) },
          },
        };
      }
      const decision = decisionOf(element.id, mapping);
      if (decision) {
        return {
          "gaik-decision-edit": {
            group: "edit",
            imageUrl: PENCIL,
            title: labels.editDecision,
            action: { click: () => ops.onDecision({ decision }) },
          },
          "gaik-decision-remove": {
            group: "edit",
            className: "bpmn-icon-trash",
            title: labels.removeDecision,
            action: { click: () => ops.onOperation([{ op: "remove_decision", decision_id: decision.id }]) },
          },
        };
      }
      if (dataObjectOf(element.id, mapping)) {
        const out: Entries = {
          "gaik-data-rename": {
            group: "edit",
            imageUrl: PENCIL,
            title: labels.renameDataObject,
            action: { click: () => this.directEditing.activate(element) },
          },
        };
        if (entries.connect) out.connect = { ...entries.connect, group: "connect", title: labels.connectData };
        return out;
      }
      const path = exceptionOf(element.id, mapping);
      if (path) {
        return {
          "gaik-rework-edit": {
            group: "edit",
            imageUrl: PENCIL,
            title: labels.editRework,
            action: { click: () => ops.onRework({ exception: path }) },
          },
          "gaik-rework-remove": {
            group: "edit",
            className: "bpmn-icon-trash",
            title: labels.removeRework,
            action: { click: () => ops.onOperation([{ op: "remove_rework_path", exception_id: path.id }]) },
          },
        };
      }
      const stepId = stepIdOf(element.id, mapping, steps);
      if (!stepId) return {};
      const out: Entries = {
        rename: {
          group: "edit",
          imageUrl: PENCIL,
          title: labels.rename,
          action: { click: () => this.directEditing.activate(element) },
        },
      };
      // A decision has no step type to change: it stays a gateway.
      if (!isDecisionStep(element.id, mapping)) {
        out[STEP_TYPE_MENU] = {
          group: "edit",
          className: "bpmn-icon-screw-wrench",
          title: labels.changeType,
          action: { click: (event: MouseEvent) => this.openTypeMenu(element, event) },
        };
      }
      const append = opForAppend(element.id, labels.newStepName, mapping, steps);
      if (append) {
        out.append = {
          group: "edit",
          imageUrl: PLUS,
          title: labels.append,
          action: { click: () => ops.onOperation([append]) },
        };
      }
      // A step is followed by one decision at most (wizard_api refuses a second).
      if (!stepHasDecision(stepId, mapping)) {
        out["gaik-add-decision"] = {
          group: "edit",
          imageUrl: SPLIT,
          title: labels.addDecision,
          action: { click: () => ops.onDecision({ after: stepId }) },
        };
      }
      out["gaik-add-rework"] = {
        group: "edit",
        imageUrl: UNDO,
        title: labels.addRework,
        action: { click: () => ops.onRework({ attachedTo: stepId }) },
      };
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
 * The `gaik-step-type` menu: the three types a step can have, each sent as
 * `set_step_type`; the step's own type is shown and does nothing. Only on a
 * step's task (`workflow.steps`): decisions, what the blueprint draws from
 * elsewhere and the manual steps get no menu. bpmn-js's replace menu is never opened.
 */
class GaikStepTypeMenu {
  static $inject = ["eventBus", "popupMenu", "config.gaikEditor"];
  constructor(
    eventBus: DiagramEventBus,
    private popupMenu: PopupMenu,
    private config: Config,
  ) {
    popupMenu.registerProvider(STEP_TYPE_MENU, this);
    eventBus.on("popupMenu.open.allowed", 2000, (e: { providerId?: string }) =>
      e.providerId === "bpmn-replace" ? false : undefined,
    );
  }
  getPopupMenuEntries(element: Element) {
    const { labels, ops } = this.config;
    const ctx = ops?.context();
    const stepId = ops && ctx && element === owner(element) ? stepIdOf(element.id, ctx.mapping, ctx.steps) : null;
    // A decision step is drawn as a gateway; turning it into a task is no type change the menu offers.
    if (!ops || !ctx || !stepId || isDecisionStep(element.id, ctx.mapping)) return {};
    const current = ops.stepType(stepId);
    const entries: Entries = {};
    for (const type of STEP_OP_TYPES) {
      entries[`gaik-step-type-${type}`] = {
        label: labels.stepTypes[type],
        imageUrl: TYPE_ICONS[type],
        // The step's own type: shown, as the one it has, and no edit.
        disabled: type === current,
        className: type === current ? "gaik-step-type-current" : undefined,
        action: () => {
          this.popupMenu.close();
          if (type !== current) ops.onOperation([{ op: "set_step_type", step_id: stepId, type }]);
        },
      };
    }
    return entries;
  }
}

/** A point on the diagram. */
type Point = { x: number; y: number };

/** The innermost lane whose box holds the point; null outside every lane. */
function laneAt(lanes: Shape[], p: Point): Shape | null {
  let best: Shape | null = null;
  for (const lane of lanes) {
    if (p.x < lane.x || p.x > lane.x + lane.width || p.y < lane.y || p.y > lane.y + lane.height) continue;
    if (!best || lane.width * lane.height < best.width * best.height) best = lane;
  }
  return best;
}

/** The innermost lane that lists the shape (`flowNodeRef`); null for one no lane lists (a data object). */
function ownLane(lanes: Shape[], shape: Shape): Shape | null {
  const bo = shape.businessObject;
  let best: Shape | null = null;
  for (const lane of lanes) {
    if (!bo || !lane.businessObject?.flowNodeRef?.includes(bo)) continue;
    if (!best || lane.width * lane.height < best.width * best.height) best = lane;
  }
  return best;
}

/**
 * Whether a drag only moves shapes where the layout keeps them: each lands,
 * by its middle, in its own lane, the one whose `flowNodeRef` lists it. A
 * lane is who does the step, which the blueprint says, so a drag into another
 * lane is no layout change (for a step on its own it is an operation,
 * `stepLaneChange`). A shape drawn outside its own lane may go back into it. A shape
 * no lane lists (a data object) stays in the lane it is drawn in, or outside
 * the lanes. A label is placed with its shape and is not kept on its own, and
 * nothing is dropped onto another parent (out of the pool, onto a flow).
 */
export function moveKeepsLanes(
  shapes: Element[],
  delta: Point | undefined,
  target: Element | undefined,
  lanes: Shape[],
): boolean {
  const moved = shapes.filter((s): s is Shape => !s.labelTarget && !isConnection(s));
  if (!moved.length) return false;
  if (target && moved.some((s) => s.parent && s.parent !== target)) return false;
  if (!delta) return true;
  return moved.every((s) => {
    const middle = { x: s.x + s.width / 2, y: s.y + s.height / 2 };
    const lands = laneAt(lanes, { x: middle.x + delta.x, y: middle.y + delta.y });
    const own = ownLane(lanes, s);
    return lands === (own ?? laneAt(lanes, middle));
  });
}

/**
 * A step dragged, on its own, into another lane than its own: the
 * `set_step_lane` that puts it there, with what the layout drops for it (its
 * place and its flows' routes). Null for anything else: several shapes, no
 * step, a drop outside the lanes or onto another parent, a lane the mapping
 * names no participant for, or a drop in its own lane.
 */
export function stepLaneChange(
  shapes: Element[],
  delta: Point | undefined,
  target: Element | undefined,
  lanes: Shape[],
  mapping: BpmnMapping,
  steps: StepRef[],
): BpmnStepLaneChange | null {
  const moved = shapes.filter((s): s is Shape => !s.labelTarget && !isConnection(s));
  if (moved.length !== 1 || !delta) return null;
  const [shape] = moved;
  if (target && shape.parent && target !== shape.parent && target.type !== "bpmn:Lane") return null;
  const middle = { x: shape.x + shape.width / 2, y: shape.y + shape.height / 2 };
  const lands = laneAt(lanes, { x: middle.x + delta.x, y: middle.y + delta.y });
  if (!lands) return null;
  const own = ownLane(lanes, shape) ?? laneAt(lanes, middle);
  const op = opForStepLane(shape.id, lands.id, own?.id ?? null, mapping, steps);
  if (!op) return null;
  const edges = [...(shape.incoming ?? []), ...(shape.outgoing ?? [])]
    .map((c) => c.id)
    .filter((id) => LAYOUT_ID.test(id));
  return { op, shapes: LAYOUT_ID.test(shape.id) ? [shape.id] : [], edges };
}

/**
 * What the keyboard and the mouse may still do: Delete removes one step or
 * one flow between steps; lines start and end at steps; nothing is created,
 * resized, copied or reconnected (no operation keeps that); lanes and pools
 * stay where the drawing puts them. Shapes move within their lane, and a
 * flow's bends move, as a layout; a step on its own may go into another lane,
 * as an operation. None of this while an edit is on its way or a name is
 * typed in place (the diagram drawn after it would drop the move).
 */
class GaikRules extends RuleProvider {
  static $inject = ["eventBus", "config.gaikEditor", "elementRegistry"];
  constructor(
    eventBus: DiagramEventBus,
    private config: Config,
    private registry: ElementRegistry,
  ) {
    super(eventBus);
  }
  init() {
    const ctx = () => this.config.ops?.context() ?? null;
    const isStep = (el?: Element) => {
      const c = ctx();
      return Boolean(el && c && stepIdOf(owner(el).id, c.mapping, c.steps));
    };
    const isData = (el?: Element) => {
      const c = ctx();
      return Boolean(el && c && dataObjectOf(owner(el).id, c.mapping));
    };
    this.addRule("elements.delete", 2000, (context: { elements: Element[] }) => {
      const c = ctx();
      if (!c || context.elements.length !== 1) return false;
      const [el] = context.elements;
      // A data object has tools but no Delete: only what an operation removes goes.
      return el === owner(el) && opForDeleteKey(canvasElement(el), c.mapping, c.steps) ? [el] : false;
    });
    this.addRule("shape.resize", 2000, () => false);
    this.addRule(["shape.create", "elements.create", "elements.paste", "element.copy", "shape.attach"], 2000, () => false);
    this.addRule("connection.start", 2000, (context: { source?: Element }) =>
      isStep(context.source) || isData(context.source) ? undefined : false,
    );
    // Between two steps (a flow), or a data object and a step (bpmn-js makes it a data association).
    this.addRule("connection.create", 2000, (context: { source?: Element; target?: Element }) => {
      const { source, target } = context;
      if (isStep(source) && isStep(target)) return source !== target ? undefined : false;
      // Only a task holds a data association: a decision step is drawn as a gateway.
      const isTask = (el?: Element) => isStep(el) && holdsData(owner(el as Element).type);
      return (isData(source) && isTask(target)) || (isTask(source) && isData(target)) ? undefined : false;
    });
    this.addRule("connection.reconnect", 2000, () => false);
    this.addRule(
      "elements.move",
      2000,
      (context: { shapes?: Element[]; delta?: Point; target?: Element }) => {
        const shapes = context.shapes ?? [];
        const c = ctx();
        if (!c || shapes.some((s) => FIXED.has(s.type))) return false;
        const lanes = this.registry.getAll().filter((el): el is Shape => el.type === "bpmn:Lane" && !isConnection(el));
        if (moveKeepsLanes(shapes, context.delta, context.target, lanes)) return undefined;
        // A step into another lane: who does it changes (set_step_lane).
        return stepLaneChange(shapes, context.delta, context.target, lanes, c.mapping, c.steps) ? undefined : false;
      },
    );
    this.addRule("connection.updateWaypoints", 2000, (context: { connection?: Element }) =>
      ctx() && context.connection && LAYOUT_ID.test(context.connection.id) ? undefined : false,
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
  static $inject = ["eventBus", "config.gaikEditor", "elementRegistry", "keyboard", "contextPad"];
  private depth = 0;
  private top: { command: string; context: Record<string, unknown> } | null = null;
  private nested = new Set<string>();
  private shapes = new Set<Shape>();
  private edges = new Set<Connection>();
  /** A step's drag into another lane, read before the move updates the lanes' lists. */
  private laneChange: BpmnStepLaneChange | null = null;

  constructor(
    eventBus: DiagramEventBus,
    private config: Config,
    private registry: ElementRegistry,
    keyboard: Keyboard,
    contextPad: { close: () => void },
  ) {
    eventBus.on("commandStack.preExecute", (e: { command: string; context: Record<string, unknown> }) => {
      this.depth += 1;
      if (this.depth === 1) {
        this.top = { command: e.command, context: e.context };
        if (e.command === "elements.move") this.laneChange = this.readLaneChange(e.context);
      } else this.nested.add(e.command);
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
      const laneChange = this.laneChange;
      this.reset();
      if (e.trigger !== "execute" || !top) return;
      // Out of bpmn-js's command stack before anything else happens.
      window.setTimeout(() => this.handle(top, nested, shapes, edges, laneChange), 0);
    });
    eventBus.on("diagram.clear", () => this.reset());

    eventBus.on("keyboard.keydown", 2000, (e: { keyEvent: KeyboardEvent }) => {
      const event = e.keyEvent;
      if (keyboard.isCmd(event) && keyboard.isKey(["z", "Z", "y", "Y"], event)) return true;
      return undefined;
    });

    // While a name is typed in place the context pad goes: its tools would start an edit over it.
    eventBus.on("directEditing.activate", () => contextPad.close());

    // Double-click and the E key rename in place: a step, a lane or a data object.
    eventBus.on("directEditing.activate.allowed", 2000, (e: { element: Element }) => {
      const c = this.config.ops?.context();
      const id = owner(e.element).id;
      return c && (stepIdOf(id, c.mapping, c.steps) || laneIdOf(id, c.mapping) || dataObjectOf(id, c.mapping))
        ? undefined
        : false;
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
    this.laneChange = null;
  }

  private readLaneChange(context: Record<string, unknown>): BpmnStepLaneChange | null {
    const c = this.config.ops?.context();
    if (!c) return null;
    const lanes = this.registry.getAll().filter((el): el is Shape => el.type === "bpmn:Lane" && !isConnection(el));
    return stepLaneChange(
      (context.shapes as Element[] | undefined) ?? [],
      context.delta as Point | undefined,
      undefined,
      lanes,
      c.mapping,
      c.steps,
    );
  }

  private handle(
    top: { command: string; context: Record<string, unknown> },
    nested: Set<string>,
    shapes: Set<Shape>,
    edges: Set<Connection>,
    laneChange: BpmnStepLaneChange | null,
  ) {
    const ops = this.config.ops;
    if (!ops) return;
    const ctx = ops.context();
    const send = (op: BlueprintOperation | null) => (op ? ops.onOperation([op]) : ops.onRevert());
    switch (top.command) {
      case "element.updateLabel": {
        const element = top.context.element as Element | undefined;
        if (!ctx || !element) return ops.onRevert();
        if (owner(element).type === "bpmn:Lane") {
          const oldLabel = top.context.oldLabel as string | undefined;
          return send(opForLaneRename(owner(element).id, top.context.newLabel as string, oldLabel, ctx.mapping));
        }
        if (dataObjectOf(owner(element).id, ctx.mapping)) {
          const oldLabel = top.context.oldLabel as string | undefined;
          return send(opForDataObjectRename(owner(element).id, top.context.newLabel as string, oldLabel, ctx.mapping));
        }
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
        return send(opForDeleteKey(canvasElement(elements[0]), ctx.mapping, ctx.steps));
      }
    }
    if (MOVE_ROOTS.has(top.command) && [...nested].every((c) => MOVE_COMMANDS.has(c))) {
      // A step into another lane is no layout: who does it changes.
      if (laneChange) return ops.onStepLane(laneChange);
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
  __init__: ["gaikPalette", "gaikContextPad", "gaikStepTypeMenu", "gaikRules", "gaikOperations"],
  gaikPalette: ["type", GaikPalette],
  gaikContextPad: ["type", GaikContextPad],
  gaikStepTypeMenu: ["type", GaikStepTypeMenu],
  gaikRules: ["type", GaikRules],
  gaikOperations: ["type", GaikOperations],
};
