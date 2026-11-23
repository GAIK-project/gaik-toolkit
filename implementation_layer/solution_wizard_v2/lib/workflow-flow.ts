/**
 * The Workflow tab's simple flow view: the blueprint's steps as one node each,
 * with arrows in their order and a human review's outcomes.
 *
 * The blueprint is the one source. Every node is a step of `blueprint.steps`,
 * and an edit here is a new blueprint (rename, add, remove), saved the way the
 * Blueprint form saves. The BPMN the server generates from the blueprint is
 * only read: it says who does a step (its lane) and what a review's "no"
 * leads to. Without it the flow is drawn from the steps alone.
 *
 * The layout is written by hand, since the flow is a line with short
 * branches: the steps run in rows that wrap like text, or in one column on a
 * narrow canvas, whichever shows them largest.
 */
import { stepIdToBpmnId } from "@/lib/bpmn-edit-state";
import { APPROVE_FLOW } from "@/lib/case-process";
import type { Blueprint, BlueprintStep, BlueprintStepType } from "@/lib/mock-sessions";

// -- the process, as the BPMN has it --------------------------------------------

/**
 * Lanes, flow nodes and sequence flows: the part of the process the flow
 * reads. The `process` of wizard_api's /cases/model (lib/case-process) has
 * the same shape, so either can be given.
 */
export type FlowProcess = {
  lanes: { id: string; name: string }[];
  nodes: { id: string; kind: string; lane: string | null }[];
  flows: { from: string; to: string; name: string }[];
};

type BpmnRef = { id?: string };
type BpmnLane = { id?: string; name?: string; flowNodeRef?: BpmnRef[] };
/** A BPMN model as bpmn-moddle's fromXML() gives it, cut down to what is read here. */
export type BpmnModel = {
  $type?: string;
  id?: string;
  name?: string;
  rootElements?: BpmnModel[];
  flowElements?: BpmnModel[];
  laneSets?: { lanes?: BpmnLane[] }[];
  sourceRef?: BpmnRef;
  targetRef?: BpmnRef;
};

const FLOW_NODE = /(Task|Event|Gateway|CallActivity|SubProcess)$/;

/** "bpmn:UserTask" → "userTask", the kind names lib/case-process uses. */
function kindOf(type: string): string {
  const local = type.replace(/^bpmn:/, "");
  return local.charAt(0).toLowerCase() + local.slice(1);
}

/** The process of a BPMN model; empty when the model has none. */
export function processFromBpmn(definitions: BpmnModel | null | undefined): FlowProcess {
  const process = (definitions?.rootElements ?? []).find((el) => el.$type === "bpmn:Process");
  const nodes = new Map<string, FlowProcess["nodes"][number]>();
  const flows: FlowProcess["flows"] = [];
  for (const el of process?.flowElements ?? []) {
    const type = el.$type ?? "";
    if (type === "bpmn:SequenceFlow") {
      if (el.sourceRef?.id && el.targetRef?.id) {
        flows.push({ from: el.sourceRef.id, to: el.targetRef.id, name: (el.name ?? "").trim() });
      }
    } else if (el.id && FLOW_NODE.test(type)) {
      nodes.set(el.id, { id: el.id, kind: kindOf(type), lane: null });
    }
  }
  const lanes: FlowProcess["lanes"] = [];
  for (const set of process?.laneSets ?? []) {
    for (const lane of set.lanes ?? []) {
      if (!lane.id) continue;
      lanes.push({ id: lane.id, name: (lane.name ?? "").replace(/\s+/g, " ").trim() });
      for (const ref of lane.flowNodeRef ?? []) {
        const node = ref.id ? nodes.get(ref.id) : undefined;
        if (node) node.lane = lane.id;
      }
    }
  }
  return { lanes, nodes: [...nodes.values()], flows };
}

// -- the flow: nodes and edges ---------------------------------------------------

export type FlowStep = {
  kind: "step";
  /** The blueprint step's id. */
  id: string;
  index: number;
  name: string;
  type: BlueprintStepType;
  /** Who or what does the step: its lane in the process. Null when the process does not say. */
  actor: string | null;
};

/** One way a review can end, other than going on to the next step. */
export type FlowOutcome =
  /** The review is the last step: an approval finishes the work. */
  | { outcome: "approved" }
  /** `returnsTo`: the index of the step the work goes back to; null when it ends there. */
  | { outcome: "rejected"; returnsTo: number | null };

export type FlowOutcomes = {
  kind: "outcomes";
  id: string;
  /** The review step these belong to. */
  of: string;
  lines: FlowOutcome[];
};

export type FlowNode = FlowStep | FlowOutcomes;

export type FlowEdge = {
  id: string;
  /** "next": on to the following step. "branch": from a review to its outcomes. */
  kind: "next" | "branch";
  from: string;
  to: string;
  /** "approved" on the arrow that leaves a review with two outcomes. */
  label: "approved" | null;
};

export type FlowModel = { nodes: FlowNode[]; edges: FlowEdge[] };

const isStep = (node: FlowNode): node is FlowStep => node.kind === "step";
const isOutcomes = (node: FlowNode): node is FlowOutcomes => node.kind === "outcomes";

/**
 * What a review's "no" leads to, or null when the review has one way out.
 * The generator draws an "Approved?" gateway after every human review, whose
 * other branch ends the process or loops back to a named step; that is assumed
 * for a step the process does not know yet (the diagram is still being drawn,
 * or the step was just added).
 */
function rejection(
  step: BlueprintStep,
  steps: BlueprintStep[],
  process: FlowProcess | null,
): { returnsTo: number | null } | null {
  if (step.type !== "human_review") return null;
  const assumed = { returnsTo: null };
  if (!process) return assumed;
  const byId = new Map(process.nodes.map((n) => [n.id, n]));
  const taskId = stepIdToBpmnId(step.id);
  if (!byId.has(taskId)) return assumed;
  const out = (id: string) => process.flows.filter((f) => f.from === id);
  const gateway = out(taskId)
    .map((f) => byId.get(f.to))
    .find((n) => n && /Gateway$/.test(n.kind));
  if (!gateway) return null;
  const branches = out(gateway.id);
  if (branches.length < 2) return null;
  const approve = branches.find((f) => APPROVE_FLOW.test(f.name)) ?? branches[0];
  const other = branches.find((f) => f !== approve);
  const back = other ? steps.findIndex((s) => stepIdToBpmnId(s.id) === other.to) : -1;
  return { returnsTo: back >= 0 ? back : null };
}

/** The flow of a blueprint's steps; `process` adds who does each step and where a rejection goes. */
export function buildFlow(steps: BlueprintStep[], process: FlowProcess | null): FlowModel {
  const laneOf = new Map(process?.nodes.map((n) => [n.id, n.lane]) ?? []);
  const laneName = new Map(process?.lanes.map((l) => [l.id, l.name]) ?? []);
  const nodes: FlowNode[] = [];
  const edges: FlowEdge[] = [];
  steps.forEach((step, index) => {
    const lane = laneOf.get(stepIdToBpmnId(step.id));
    nodes.push({
      kind: "step",
      id: step.id,
      index,
      name: step.name,
      type: step.type,
      actor: (lane && laneName.get(lane)) || null,
    });
    const next = steps[index + 1];
    const rejected = rejection(step, steps, process);
    if (rejected) {
      const lines: FlowOutcome[] = [{ outcome: "rejected", ...rejected }];
      if (!next) lines.unshift({ outcome: "approved" });
      const id = `${step.id}:outcomes`;
      nodes.push({ kind: "outcomes", id, of: step.id, lines });
      edges.push({ id: `${step.id}>outcomes`, kind: "branch", from: step.id, to: id, label: null });
    }
    if (next) {
      edges.push({
        id: `${step.id}>${next.id}`,
        kind: "next",
        from: step.id,
        to: next.id,
        label: rejected ? "approved" : null,
      });
    }
  });
  return { nodes, edges };
}

// -- light edits: each gives the blueprint to save --------------------------------

/** The blueprint with one step renamed. Only the name changes: the type, component and settings stay. */
export function renameStep(blueprint: Blueprint, stepId: string, name: string): Blueprint {
  return { ...blueprint, steps: blueprint.steps.map((s) => (s.id === stepId ? { ...s, name } : s)) };
}

/** An id no step has yet, in the Blueprint form's style ("step_k3x9qa"). */
export function newStepId(steps: { id: string }[], random: () => number = Math.random): string {
  const taken = new Set(steps.map((s) => s.id));
  for (;;) {
    const id = `step_${random().toString(36).slice(2, 8).padEnd(6, "0")}`;
    if (!taken.has(id)) return id;
  }
}

/** The blueprint with `step` after the step `afterId`; at the end when there is no such step. */
export function insertStepAfter(blueprint: Blueprint, afterId: string | null, step: BlueprintStep): Blueprint {
  const at = blueprint.steps.findIndex((s) => s.id === afterId);
  const steps = [...blueprint.steps];
  steps.splice(at < 0 ? steps.length : at + 1, 0, step);
  return { ...blueprint, steps };
}

/** The blueprint without one step. */
export function removeStep(blueprint: Blueprint, stepId: string): Blueprint {
  return { ...blueprint, steps: blueprint.steps.filter((s) => s.id !== stepId) };
}

// -- layout ------------------------------------------------------------------------

export type Point = { x: number; y: number };
export type Box = { x: number; y: number; width: number; height: number };
export type Size = { width: number; height: number };

/** Sizes in the flow's own units (px at 100 %). */
export const FLOW_METRICS = {
  stepWidth: 208,
  stepHeight: 68,
  outcomesWidth: 196,
  outcomeLine: 20,
  outcomesPad: 6,
  /** Between two steps in a row. */
  gap: 44,
  /** Between a review and the next step in its row: room for "Approves" on the arrow. */
  labelGap: 96,
  /** Between rows; the line back to the start of the next row runs in its middle. */
  rowGap: 44,
  /** Between a review and its outcomes. */
  branchGap: 14,
  /** Beside the rows, where the line to the next row turns. */
  margin: 18,
  /** In one column: the line runs this far from the steps' left edge, under their numbers. */
  rail: 24,
  /** In one column: a review's outcomes start this far right of the line. */
  railClear: 12,
  /** Between two steps in one column. */
  columnGap: 28,
  labelHeight: 18,
} as const;

const M = FLOW_METRICS;

export type FlowLayout = {
  /** Steps in a row; 1 is one column. */
  columns: number;
  boxes: Map<string, Box>;
  /** Each edge as a line through `points`, and where its label goes. */
  edges: Map<string, { points: Point[]; label: Point | null }>;
  bounds: Box;
};

export function outcomesHeight(node: FlowOutcomes): number {
  return M.outcomesPad * 2 + node.lines.length * M.outcomeLine;
}

/** The steps in rows of `columns`, or in one column. */
export function layoutFlow(model: FlowModel, columns: number): FlowLayout {
  const steps = model.nodes.filter(isStep);
  const outcomesOf = new Map(model.nodes.filter(isOutcomes).map((o) => [o.of, o]));
  const nextOf = new Map(model.edges.filter((e) => e.kind === "next").map((e) => [e.from, e]));
  const boxes = new Map<string, Box>();
  const edges: FlowLayout["edges"] = new Map();
  const step = (x: number, y: number): Box => ({ x, y, width: M.stepWidth, height: M.stepHeight });
  const midY = (box: Box) => box.y + box.height / 2;

  if (columns <= 1) {
    let y = 0;
    let height = 0;
    let width = steps.length ? M.stepWidth : 0;
    const labelAt = new Map<string, Point>();
    for (const s of steps) {
      boxes.set(s.id, step(0, y));
      let bottom = y + M.stepHeight;
      const outcomes = outcomesOf.get(s.id);
      if (outcomes) {
        const h = outcomesHeight(outcomes);
        // Right of the line, which goes on down past them.
        const x = M.rail + M.railClear;
        boxes.set(outcomes.id, { x, y: bottom + M.branchGap, width: M.outcomesWidth, height: h });
        width = Math.max(width, x + M.outcomesWidth);
        bottom += M.branchGap + h;
      }
      height = bottom;
      const next = nextOf.get(s.id);
      if (next?.label) {
        // Under the outcomes, so the label does not sit beside them on the line.
        labelAt.set(next.id, { x: M.rail + 22, y: bottom + 8 + M.labelHeight / 2 });
        bottom += 8 + M.labelHeight;
      }
      y = bottom + M.columnGap;
    }
    for (const edge of model.edges) {
      const a = boxes.get(edge.from);
      const b = boxes.get(edge.to);
      if (!a || !b) continue;
      if (edge.kind === "branch") {
        const x = b.x + b.width / 2;
        edges.set(edge.id, { points: [{ x, y: a.y + a.height }, { x, y: b.y }], label: null });
      } else {
        edges.set(edge.id, {
          points: [{ x: M.rail, y: a.y + a.height }, { x: M.rail, y: b.y }],
          label: labelAt.get(edge.id) ?? null,
        });
      }
    }
    return { columns: 1, boxes, edges, bounds: { x: 0, y: 0, width, height } };
  }

  const rows: FlowStep[][] = [];
  for (let i = 0; i < steps.length; i += columns) rows.push(steps.slice(i, i + columns));
  const wraps = rows.length > 1;
  const left = wraps ? M.margin : 0;
  const rowOf = new Map<string, number>();
  const rowBottom: number[] = [];
  let right = 0;
  let y = 0;
  rows.forEach((row, r) => {
    let x = left;
    let bottom = y + M.stepHeight;
    row.forEach((s, j) => {
      boxes.set(s.id, step(x, y));
      rowOf.set(s.id, r);
      const outcomes = outcomesOf.get(s.id);
      if (outcomes) {
        const h = outcomesHeight(outcomes);
        boxes.set(outcomes.id, {
          x: x + (M.stepWidth - M.outcomesWidth) / 2,
          y: y + M.stepHeight + M.branchGap,
          width: M.outcomesWidth,
          height: h,
        });
        bottom = Math.max(bottom, y + M.stepHeight + M.branchGap + h);
      }
      right = Math.max(right, x + M.stepWidth);
      if (j < row.length - 1) x += M.stepWidth + (nextOf.get(s.id)?.label ? M.labelGap : M.gap);
    });
    rowBottom.push(bottom);
    y = bottom + M.rowGap;
  });
  for (const edge of model.edges) {
    const a = boxes.get(edge.from);
    const b = boxes.get(edge.to);
    if (!a || !b) continue;
    if (edge.kind === "branch") {
      const x = a.x + a.width / 2;
      edges.set(edge.id, { points: [{ x, y: a.y + a.height }, { x, y: b.y }], label: null });
    } else if (a.y === b.y) {
      const from = { x: a.x + a.width, y: midY(a) };
      const to = { x: b.x, y: midY(b) };
      edges.set(edge.id, {
        points: [from, to],
        label: edge.label ? { x: (from.x + to.x) / 2, y: from.y } : null,
      });
    } else {
      // To the start of the next row, as a line of text wraps: out to the
      // right, along the gap under this row (and under its outcomes), and in
      // from the left.
      const run = (rowBottom[rowOf.get(edge.from) ?? 0] ?? a.y + a.height) + M.rowGap / 2;
      const out = a.x + a.width + M.margin;
      const back = b.x - M.margin;
      edges.set(edge.id, {
        points: [
          { x: a.x + a.width, y: midY(a) },
          { x: out, y: midY(a) },
          { x: out, y: run },
          { x: back, y: run },
          { x: back, y: midY(b) },
          { x: b.x, y: midY(b) },
        ],
        label: edge.label ? { x: a.x + a.width - 40, y: run } : null,
      });
    }
  }
  return {
    columns,
    boxes,
    edges,
    bounds: { x: 0, y: 0, width: right + (wraps ? M.margin : 0), height: rowBottom.at(-1) ?? 0 },
  };
}

/** How large the flow can be shown in `canvas` without cutting anything off (never above 100 %). */
function wholeZoom(bounds: Box, canvas: Size): number {
  if (bounds.width <= 0 || bounds.height <= 0) return 1;
  return Math.max(0, Math.min(canvas.width / bounds.width, canvas.height / bounds.height, 1));
}

/**
 * How many steps go in a row on a canvas of this size: the arrangement that
 * shows the whole flow largest. Among arrangements that are about as large
 * (within 15 %), the one with the fewest rows reads most like a line; with the
 * same number of rows, the larger one, whose rows are also the more even.
 *
 * A flow that no arrangement shows whole at `minZoom` or larger is read by
 * scrolling down (see fitViewport), so only its width has to fit: the most
 * steps in a row that do.
 */
export function chooseColumns(model: FlowModel, canvas: Size, minZoom = 0.5, most = 6): number {
  const count = model.nodes.filter(isStep).length;
  if (count <= 1) return 1;
  const fits = [];
  for (let columns = 1; columns <= Math.min(count, most); columns++) {
    const { bounds } = layoutFlow(model, columns);
    fits.push({
      columns,
      rows: Math.ceil(count / columns),
      zoom: wholeZoom(bounds, canvas),
      wide: bounds.width > 0 ? canvas.width / bounds.width : 1,
    });
  }
  const largest = Math.max(...fits.map((f) => f.zoom));
  if (largest < minZoom) {
    return fits.filter((f) => f.wide >= minZoom).at(-1)?.columns ?? 1;
  }
  return fits
    .filter((f) => f.zoom >= Math.max(largest * 0.85, minZoom))
    .sort((a, b) => a.rows - b.rows || b.zoom - a.zoom)[0].columns;
}

export type Viewport = { x: number; y: number; zoom: number };
export type Inset = { top: number; right: number; bottom: number; left: number };

/**
 * The view that shows the whole flow, centred in the canvas inside `inset`
 * (what the controls cover). A flow too long to stay readable is not shrunk
 * below `minZoom`: it starts at the top, and the rest is a scroll away.
 */
export function fitViewport(
  bounds: Box,
  canvas: Size,
  inset: Inset,
  { minZoom = 0.3, maxZoom = 1 }: { minZoom?: number; maxZoom?: number } = {},
): Viewport {
  const room = {
    width: Math.max(1, canvas.width - inset.left - inset.right),
    height: Math.max(1, canvas.height - inset.top - inset.bottom),
  };
  if (bounds.width <= 0 || bounds.height <= 0) return { x: inset.left, y: inset.top, zoom: maxZoom };
  const whole = Math.min(room.width / bounds.width, room.height / bounds.height, maxZoom);
  const fits = whole >= minZoom;
  const zoom = fits ? whole : Math.min(maxZoom, Math.max(minZoom, Math.min(room.width / bounds.width, maxZoom)));
  const width = bounds.width * zoom;
  const height = bounds.height * zoom;
  return {
    x: inset.left - bounds.x * zoom + (width <= room.width ? (room.width - width) / 2 : 0),
    y: inset.top - bounds.y * zoom + (height <= room.height ? (room.height - height) / 2 : 0),
    zoom,
  };
}

/**
 * Where a step's menu goes on the canvas: under its node, above it when there
 * is no room below, and always whole inside the canvas. `anchor` is the node
 * on screen, in the canvas's own pixels. `covers` says the menu had room on
 * neither side and lies over its node.
 */
export function placeMenu(anchor: Box, menu: Size, canvas: Size, gap = 8): Point & { covers: boolean } {
  const within = (value: number, low: number, high: number) => Math.max(low, Math.min(value, Math.max(low, high)));
  const below = anchor.y + anchor.height + gap;
  const above = anchor.y - menu.height - gap;
  const fitsBelow = below + menu.height <= canvas.height - gap;
  const fitsAbove = above >= gap;
  return {
    x: within(anchor.x, gap, canvas.width - menu.width - gap),
    y: within(fitsBelow || !fitsAbove ? below : above, gap, canvas.height - menu.height - gap),
    covers: !fitsBelow && !fitsAbove,
  };
}

/** An SVG path through `points` with its corners rounded. */
export function roundedPath(points: Point[], radius = 8): string {
  if (points.length === 0) return "";
  const n = (v: number) => String(Math.round(v * 100) / 100);
  let d = `M ${n(points[0].x)} ${n(points[0].y)}`;
  for (let i = 1; i < points.length; i++) {
    const cur = points[i];
    const next = points[i + 1];
    if (!next) {
      d += ` L ${n(cur.x)} ${n(cur.y)}`;
      break;
    }
    const prev = points[i - 1];
    const before = Math.hypot(cur.x - prev.x, cur.y - prev.y);
    const after = Math.hypot(next.x - cur.x, next.y - cur.y);
    const r = Math.min(radius, before / 2, after / 2);
    if (r <= 0) {
      d += ` L ${n(cur.x)} ${n(cur.y)}`;
      continue;
    }
    const start = { x: cur.x - ((cur.x - prev.x) / before) * r, y: cur.y - ((cur.y - prev.y) / before) * r };
    const end = { x: cur.x + ((next.x - cur.x) / after) * r, y: cur.y + ((next.y - cur.y) / after) * r };
    d += ` L ${n(start.x)} ${n(start.y)} Q ${n(cur.x)} ${n(cur.y)} ${n(end.x)} ${n(end.y)}`;
  }
  return d;
}
