import { BpmnModdle } from "bpmn-moddle";
import { describe, expect, it } from "vitest";
import { blueprintPayload } from "./blueprint-draft";
import type { Blueprint, BlueprintStep } from "./mock-sessions";
import {
  FLOW_METRICS as M,
  buildFlow,
  chooseColumns,
  fitViewport,
  insertStepAfter,
  layoutFlow,
  newStepId,
  placeMenu,
  processFromBpmn,
  removeStep,
  renameStep,
  roundedPath,
  type BpmnModel,
  type Box,
  type FlowModel,
  type FlowProcess,
  type Point,
} from "./workflow-flow";

// The invoice process of the mock store: two automatic steps, a review, an export.
const STEPS: BlueprintStep[] = [
  { id: "ingest", name: "Invoice intake", type: "io" },
  { id: "extract", name: "Data extraction", type: "ai", component: "docling" },
  { id: "classify", name: "Classification", type: "ai", component: "LLM" },
  { id: "approve", name: "Approval", type: "human_review" },
  { id: "export", name: "Export to finance system", type: "io" },
];

const blueprint = (steps = STEPS): Blueprint => ({
  name: "Invoices",
  description: "",
  goal: "",
  steps,
  integration_targets: ["finance_system"],
});

// What the generator writes for those steps (solution_wizard bpmn_generator),
// cut down to lanes, flow nodes and sequence flows.
function diagram({
  rejectTo = "EndEvent_rejected_approve",
  gateway = true,
}: { rejectTo?: string; gateway?: boolean } = {}) {
  const afterReview = gateway
    ? `<bpmn:sequenceFlow id="F4" sourceRef="Activity_approve" targetRef="Gateway_approve_approve" />
       <bpmn:sequenceFlow id="F5" name="Yes" sourceRef="Gateway_approve_approve" targetRef="Activity_export" />
       <bpmn:sequenceFlow id="F6" name="No" sourceRef="Gateway_approve_approve" targetRef="${rejectTo}" />`
    : `<bpmn:sequenceFlow id="F4" sourceRef="Activity_approve" targetRef="Activity_export" />`;
  return `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="Defs" targetNamespace="x">
  <bpmn:process id="Process_1" isExecutable="false">
    <bpmn:laneSet id="LaneSet_1">
      <bpmn:lane id="Lane_clerk" name="Accounts clerk">
        <bpmn:flowNodeRef>Activity_ingest</bpmn:flowNodeRef>
        <bpmn:flowNodeRef>Activity_export</bpmn:flowNodeRef>
        <bpmn:flowNodeRef>StartEvent_1</bpmn:flowNodeRef>
      </bpmn:lane>
      <bpmn:lane id="Lane_ai" name="GAIK AI  system">
        <bpmn:flowNodeRef>Activity_extract</bpmn:flowNodeRef>
        <bpmn:flowNodeRef>Activity_classify</bpmn:flowNodeRef>
      </bpmn:lane>
      <bpmn:lane id="Lane_reviewer" name="Accountant">
        <bpmn:flowNodeRef>Activity_approve</bpmn:flowNodeRef>
        <bpmn:flowNodeRef>Gateway_approve_approve</bpmn:flowNodeRef>
        <bpmn:flowNodeRef>EndEvent_rejected_approve</bpmn:flowNodeRef>
      </bpmn:lane>
    </bpmn:laneSet>
    <bpmn:startEvent id="StartEvent_1" name="Started" />
    <bpmn:userTask id="Activity_ingest" name="Invoice intake" />
    <bpmn:serviceTask id="Activity_extract" name="[D] Data extraction" />
    <bpmn:serviceTask id="Activity_classify" name="[LLM] Classification" />
    <bpmn:userTask id="Activity_approve" name="Approval" />
    <bpmn:userTask id="Activity_export" name="Export to finance system" />
    <bpmn:exclusiveGateway id="Gateway_approve_approve" name="Approved?" />
    <bpmn:endEvent id="EndEvent_rejected_approve" name="Rejected" />
    <bpmn:endEvent id="EndEvent_success" name="Done" />
    <bpmn:dataObjectReference id="DataObjectRef_json" name="Structured JSON" dataObjectRef="DataObject_json" />
    <bpmn:dataObject id="DataObject_json" />
    <bpmn:sequenceFlow id="F1" sourceRef="StartEvent_1" targetRef="Activity_ingest" />
    <bpmn:sequenceFlow id="F2" sourceRef="Activity_ingest" targetRef="Activity_extract" />
    <bpmn:sequenceFlow id="F3" sourceRef="Activity_extract" targetRef="Activity_classify" />
    <bpmn:sequenceFlow id="F3b" sourceRef="Activity_classify" targetRef="Activity_approve" />
    ${afterReview}
    <bpmn:sequenceFlow id="F7" sourceRef="Activity_export" targetRef="EndEvent_success" />
  </bpmn:process>
</bpmn:definitions>`;
}

async function processOf(xml: string): Promise<FlowProcess> {
  const { rootElement } = await new BpmnModdle().fromXML(xml);
  return processFromBpmn(rootElement as BpmnModel);
}

const stepNodes = (model: FlowModel) => model.nodes.filter((n) => n.kind === "step");
const outcomes = (model: FlowModel) => model.nodes.filter((n) => n.kind === "outcomes");

describe("processFromBpmn", () => {
  it("reads lanes, flow nodes and sequence flows, and leaves data objects out", async () => {
    const process = await processOf(diagram());
    expect(process.lanes).toEqual([
      { id: "Lane_clerk", name: "Accounts clerk" },
      { id: "Lane_ai", name: "GAIK AI system" },
      { id: "Lane_reviewer", name: "Accountant" },
    ]);
    const byId = new Map(process.nodes.map((n) => [n.id, n]));
    expect(byId.get("Activity_classify")).toEqual({ id: "Activity_classify", kind: "serviceTask", lane: "Lane_ai" });
    expect(byId.get("Activity_approve")?.kind).toBe("userTask");
    expect(byId.get("Gateway_approve_approve")?.kind).toBe("exclusiveGateway");
    expect(byId.has("DataObjectRef_json")).toBe(false);
    expect(process.flows).toContainEqual({ from: "Gateway_approve_approve", to: "Activity_export", name: "Yes" });
  });

  it("is empty for a model without a process", () => {
    expect(processFromBpmn(null)).toEqual({ lanes: [], nodes: [], flows: [] });
    expect(processFromBpmn({ rootElements: [{ $type: "bpmn:Collaboration" }] })).toEqual({
      lanes: [],
      nodes: [],
      flows: [],
    });
  });
});

describe("buildFlow", () => {
  it("draws one node a step, in the blueprint's order, with arrows between neighbours", () => {
    const model = buildFlow(STEPS.slice(0, 3), null);
    expect(stepNodes(model)).toEqual([
      { kind: "step", id: "ingest", index: 0, name: "Invoice intake", type: "io", actor: null },
      { kind: "step", id: "extract", index: 1, name: "Data extraction", type: "ai", actor: null },
      { kind: "step", id: "classify", index: 2, name: "Classification", type: "ai", actor: null },
    ]);
    expect(model.edges).toEqual([
      { id: "ingest>extract", kind: "next", from: "ingest", to: "extract", label: null },
      { id: "extract>classify", kind: "next", from: "extract", to: "classify", label: null },
    ]);
    expect(outcomes(model)).toEqual([]);
  });

  it("names who does each step by its lane in the process", async () => {
    const model = buildFlow(STEPS, await processOf(diagram()));
    expect(stepNodes(model).map((n) => n.kind === "step" && n.actor)).toEqual([
      "Accounts clerk",
      "GAIK AI system",
      "GAIK AI system",
      "Accountant",
      "Accounts clerk",
    ]);
  });

  it("leaves the actor out for a step the process does not have", async () => {
    const steps = [...STEPS, { id: "archive", name: "Archiving", type: "io" as const }];
    const model = buildFlow(steps, await processOf(diagram()));
    expect(stepNodes(model).at(-1)).toMatchObject({ id: "archive", actor: null });
  });

  it("gives a review two outcomes: the arrow on is the approval, and a rejection ends there", async () => {
    const model = buildFlow(STEPS, await processOf(diagram()));
    expect(outcomes(model)).toEqual([
      { kind: "outcomes", id: "approve:outcomes", of: "approve", lines: [{ outcome: "rejected", returnsTo: null }] },
    ]);
    expect(model.edges).toContainEqual({
      id: "approve>export",
      kind: "next",
      from: "approve",
      to: "export",
      label: "approved",
    });
    expect(model.edges).toContainEqual({
      id: "approve>outcomes",
      kind: "branch",
      from: "approve",
      to: "approve:outcomes",
      label: null,
    });
    // Only the review's arrow carries a label.
    expect(model.edges.filter((e) => e.label).map((e) => e.id)).toEqual(["approve>export"]);
  });

  it("says which step a rejection returns to when the process loops back", async () => {
    const model = buildFlow(STEPS, await processOf(diagram({ rejectTo: "Activity_ingest" })));
    expect(outcomes(model)[0]).toMatchObject({ lines: [{ outcome: "rejected", returnsTo: 0 }] });
  });

  it("draws no outcomes for a review the process lets straight through", async () => {
    const model = buildFlow(STEPS, await processOf(diagram({ gateway: false })));
    expect(outcomes(model)).toEqual([]);
    expect(model.edges.every((e) => e.label === null)).toBe(true);
  });

  it("assumes the generator's two outcomes while the process is not known", () => {
    // Before the diagram has loaded, and for a review the diagram does not have yet.
    expect(outcomes(buildFlow(STEPS, null))).toHaveLength(1);
    const added = [...STEPS, { id: "second_review", name: "Sign-off", type: "human_review" as const }];
    expect(outcomes(buildFlow(added, { lanes: [], nodes: [], flows: [] })).map((o) => o.kind === "outcomes" && o.of)).toEqual([
      "approve",
      "second_review",
    ]);
  });

  it("ends a last-step review in both its outcomes, with no arrow on", () => {
    const steps = STEPS.slice(0, 4);
    const model = buildFlow(steps, null);
    expect(outcomes(model)[0]).toMatchObject({
      of: "approve",
      lines: [{ outcome: "approved" }, { outcome: "rejected", returnsTo: null }],
    });
    expect(model.edges.filter((e) => e.from === "approve")).toEqual([
      { id: "approve>outcomes", kind: "branch", from: "approve", to: "approve:outcomes", label: null },
    ]);
  });

  it("is empty for a blueprint without steps", () => {
    expect(buildFlow([], null)).toEqual({ nodes: [], edges: [] });
  });
});

describe("light edits", () => {
  it("a rename changes the name and nothing else", () => {
    // A component-less automatic step is "io"; a rename must not turn it into "ai".
    const steps: BlueprintStep[] = [
      { id: "save", name: "Save to Excel", type: "io", description: "Writes the rows", settings: { sheet: "A" } },
      { id: "extract", name: "Extract", type: "ai", component: "LLM" },
    ];
    const before = blueprint(steps);
    const after = renameStep(before, "save", "Export the rows");
    expect(after.steps[0]).toEqual({ ...steps[0], name: "Export the rows" });
    expect(after.steps[1]).toBe(steps[1]);
    expect(after.integration_targets).toEqual(["finance_system"]);
    // The same holds for what a save sends.
    expect(blueprintPayload(after).steps.map((s) => s.type)).toEqual(["io", "ai"]);
    expect(blueprintPayload(after).steps[0].component).toBeUndefined();
    // The blueprint it was made from is left as it was.
    expect(before.steps[0].name).toBe("Save to Excel");
  });

  it("a rename of an unknown step changes nothing", () => {
    const before = blueprint();
    expect(renameStep(before, "nope", "X").steps).toEqual(before.steps);
  });

  it("adds a step after the chosen one, or at the end", () => {
    const review: BlueprintStep = { id: "check", name: "Review", type: "human_review" };
    expect(insertStepAfter(blueprint(), "extract", review).steps.map((s) => s.id)).toEqual([
      "ingest",
      "extract",
      "check",
      "classify",
      "approve",
      "export",
    ]);
    expect(insertStepAfter(blueprint(), null, review).steps.at(-1)).toEqual(review);
    expect(insertStepAfter(blueprint([]), "gone", review).steps).toEqual([review]);
  });

  it("removes one step and keeps the rest in order", () => {
    expect(removeStep(blueprint(), "approve").steps.map((s) => s.id)).toEqual(["ingest", "extract", "classify", "export"]);
  });

  it("makes an id no step has", () => {
    const rolls = [0.123456789, 0.123456789, 0.987654321];
    const id = newStepId([{ id: `step_${(0.123456789).toString(36).slice(2, 8)}` }], () => rolls.shift() ?? 0.5);
    expect(id).toBe(`step_${(0.987654321).toString(36).slice(2, 8)}`);
    expect(newStepId([])).toMatch(/^step_[0-9a-z]{6}$/);
  });
});

// -- layout ----------------------------------------------------------------------

const overlap = (a: Box, b: Box) =>
  a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;

/** Whether the straight piece from `p` to `q` passes through the inside of `box`. */
function crosses(p: Point, q: Point, box: Box): boolean {
  const minX = Math.min(p.x, q.x);
  const maxX = Math.max(p.x, q.x);
  const minY = Math.min(p.y, q.y);
  const maxY = Math.max(p.y, q.y);
  return maxX > box.x && minX < box.x + box.width && maxY > box.y && minY < box.y + box.height;
}

function manySteps(count: number, reviewAt: number[] = []): BlueprintStep[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `s${i + 1}`,
    name: `Step ${i + 1}`,
    type: reviewAt.includes(i) ? ("human_review" as const) : ("io" as const),
  }));
}

function expectTidy(model: FlowModel, columns: number) {
  const layout = layoutFlow(model, columns);
  const boxes = [...layout.boxes.entries()];
  // Every node has a place, inside the bounds, and no two share one.
  expect(boxes.map(([id]) => id).sort()).toEqual(model.nodes.map((n) => n.id).sort());
  for (const [, box] of boxes) {
    expect(box.x).toBeGreaterThanOrEqual(layout.bounds.x);
    expect(box.y).toBeGreaterThanOrEqual(layout.bounds.y);
    expect(box.x + box.width).toBeLessThanOrEqual(layout.bounds.x + layout.bounds.width);
    expect(box.y + box.height).toBeLessThanOrEqual(layout.bounds.y + layout.bounds.height);
  }
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      expect(overlap(boxes[i][1], boxes[j][1]), `${boxes[i][0]} over ${boxes[j][0]}`).toBe(false);
    }
  }
  // Every arrow is drawn, stays inside the bounds and runs through no node.
  for (const edge of model.edges) {
    const line = layout.edges.get(edge.id);
    expect(line, edge.id).toBeDefined();
    const points = line!.points;
    expect(points[0]).not.toEqual(points.at(-1));
    for (const p of points) {
      expect(p.x).toBeGreaterThanOrEqual(layout.bounds.x);
      expect(p.x).toBeLessThanOrEqual(layout.bounds.x + layout.bounds.width);
      expect(p.y).toBeLessThanOrEqual(layout.bounds.y + layout.bounds.height);
    }
    for (let i = 0; i < points.length - 1; i++) {
      for (const [id, box] of boxes) {
        expect(crosses(points[i], points[i + 1], box), `${edge.id} through ${id}`).toBe(false);
      }
    }
    // A label sits on its arrow's line, clear of every node.
    if (line!.label) {
      const half = { w: 34, h: M.labelHeight / 2 };
      const tag: Box = { x: line!.label.x - half.w, y: line!.label.y - half.h, width: half.w * 2, height: half.h * 2 };
      for (const [id, box] of boxes) expect(overlap(tag, box), `${edge.id} label over ${id}`).toBe(false);
    }
  }
  return layout;
}

describe("layoutFlow", () => {
  it("puts the steps of one row side by side, with straight arrows between them", () => {
    const model = buildFlow(STEPS.slice(0, 3), null);
    const layout = expectTidy(model, 3);
    const [a, b, c] = ["ingest", "extract", "classify"].map((id) => layout.boxes.get(id)!);
    expect(a.y).toBe(b.y);
    expect(b.y).toBe(c.y);
    expect(b.x).toBe(a.x + M.stepWidth + M.gap);
    expect(layout.edges.get("ingest>extract")!.points).toEqual([
      { x: a.x + M.stepWidth, y: a.y + M.stepHeight / 2 },
      { x: b.x, y: b.y + M.stepHeight / 2 },
    ]);
    expect(layout.bounds).toEqual({ x: 0, y: 0, width: 3 * M.stepWidth + 2 * M.gap, height: M.stepHeight });
  });

  it("wraps to the next row like a line of text, under the row's outcomes", () => {
    // Step 3 is a review at the end of the first row.
    const model = buildFlow(manySteps(5, [2]), null);
    const layout = expectTidy(model, 3);
    const review = layout.boxes.get("s3")!;
    const box = layout.boxes.get("s3:outcomes")!;
    const next = layout.boxes.get("s4")!;
    expect(next.x).toBe(layout.boxes.get("s1")!.x);
    expect(next.y).toBeGreaterThan(box.y + box.height);
    const { points, label } = layout.edges.get("s3>s4")!;
    // Out of the review's right side, into the next step's left side.
    expect(points[0]).toEqual({ x: review.x + review.width, y: review.y + review.height / 2 });
    expect(points.at(-1)).toEqual({ x: next.x, y: next.y + next.height / 2 });
    const run = points[2].y;
    expect(run).toBeGreaterThan(box.y + box.height);
    expect(run).toBeLessThan(next.y);
    expect(label?.y).toBe(run);
  });

  it("widens the gap after a review for its label, and hangs its outcomes under it", () => {
    const model = buildFlow(manySteps(4, [1]), null);
    const layout = expectTidy(model, 4);
    const review = layout.boxes.get("s2")!;
    expect(layout.boxes.get("s3")!.x - (review.x + review.width)).toBe(M.labelGap);
    expect(layout.boxes.get("s2")!.x - (layout.boxes.get("s1")!.x + M.stepWidth)).toBe(M.gap);
    const box = layout.boxes.get("s2:outcomes")!;
    expect(box.y).toBe(review.y + review.height + M.branchGap);
    expect(box.x + box.width / 2).toBe(review.x + review.width / 2);
    expect(layout.edges.get("s2>s3")!.label).toEqual({
      x: review.x + review.width + M.labelGap / 2,
      y: review.y + review.height / 2,
    });
  });

  it("stacks the steps in one column, the line under their numbers", () => {
    const model = buildFlow(manySteps(4, [1]), null);
    const layout = expectTidy(model, 1);
    expect(layout.columns).toBe(1);
    const ys = ["s1", "s2", "s3", "s4"].map((id) => layout.boxes.get(id)!.y);
    expect([...ys].sort((a, b) => a - b)).toEqual(ys);
    expect(new Set(["s1", "s2", "s3", "s4"].map((id) => layout.boxes.get(id)!.x))).toEqual(new Set([0]));
    expect(layoutFlow(buildFlow(manySteps(4), null), 1).bounds.width).toBe(M.stepWidth);
    for (const id of ["s1>s2", "s2>s3", "s3>s4"]) {
      expect(layout.edges.get(id)!.points.map((p) => p.x)).toEqual([M.rail, M.rail]);
    }
    // The review's outcomes hang to the right of the line.
    expect(layout.boxes.get("s2:outcomes")!.x).toBeGreaterThan(M.rail);
  });

  it.each([
    [1, 1],
    [2, 2],
    [3, 5],
    [3, 8],
    [4, 9],
    [2, 12],
    [5, 12],
  ])("is tidy with %i in a row and %i steps, reviews among them", (columns, count) => {
    expectTidy(buildFlow(manySteps(count, [1, count - 1]), null), columns);
    expectTidy(buildFlow(manySteps(count, [0, 2, 3]), null), columns);
  });

  it("gives an empty flow no size", () => {
    expect(layoutFlow(buildFlow([], null), 3).bounds).toEqual({ x: 0, y: 0, width: 0, height: 0 });
    expect(layoutFlow(buildFlow([], null), 1).bounds).toEqual({ x: 0, y: 0, width: 0, height: 0 });
  });
});

describe("chooseColumns", () => {
  // The canvas beside the open chat in a 1440 x 900 window, less what the controls cover.
  const besideChat = { width: 718, height: 440 };
  const wide = { width: 1300, height: 520 };
  const phone = { width: 332, height: 420 };

  it("keeps a short flow on one row when it fits", () => {
    expect(chooseColumns(buildFlow(manySteps(3, [2]), null), besideChat)).toBe(3);
    expect(chooseColumns(buildFlow(manySteps(5, [3]), null), wide)).toBe(5);
  });

  it("wraps a longer flow into the fewest rows that stay readable", () => {
    expect(chooseColumns(buildFlow(STEPS, null), besideChat)).toBe(3);
    expect(chooseColumns(buildFlow(manySteps(8, [6]), null), besideChat)).toBe(3);
    // Four steps beside the chat: two even rows rather than three and one.
    expect(chooseColumns(buildFlow(manySteps(4), null), besideChat)).toBe(2);
  });

  it("uses one column on a phone, also for a flow too long to show whole", () => {
    expect(chooseColumns(buildFlow(STEPS, null), phone, 0.85)).toBe(1);
    // Nine steps would be largest two in a row at 61 %; one column at full size scrolls instead.
    expect(chooseColumns(buildFlow(manySteps(9, [4]), null), phone, 0.85)).toBe(1);
  });

  it("never picks rows wider than the canvas shows at the smallest readable size", () => {
    // Forty steps: six in a row would be 48 %, under the 50 % floor; five fit whole at 54 %.
    const forty = buildFlow(manySteps(40), null);
    expect(chooseColumns(forty, besideChat)).toBe(5);
    // Eighty steps fit whole in no arrangement, so they scroll: the widest rows that are readable.
    const eighty = buildFlow(manySteps(80), null);
    const columns = chooseColumns(eighty, besideChat);
    expect(columns).toBe(5);
    expect(layoutFlow(eighty, columns).bounds.width * 0.5).toBeLessThanOrEqual(besideChat.width);
  });

  it("has nothing to choose for one step or none", () => {
    expect(chooseColumns(buildFlow(manySteps(1), null), besideChat)).toBe(1);
    expect(chooseColumns(buildFlow([], null), besideChat)).toBe(1);
  });
});

describe("fitViewport", () => {
  const inset = { top: 52, right: 16, bottom: 16, left: 16 };
  const shown = (bounds: Box, view: { x: number; y: number; zoom: number }): Box => ({
    x: bounds.x * view.zoom + view.x,
    y: bounds.y * view.zoom + view.y,
    width: bounds.width * view.zoom,
    height: bounds.height * view.zoom,
  });

  it.each([
    ["five steps beside the chat", STEPS, { width: 750, height: 552 }],
    ["eight steps beside the chat", manySteps(8, [2, 6]), { width: 750, height: 552 }],
    ["twelve steps beside the chat", manySteps(12, [5]), { width: 750, height: 552 }],
    ["eight steps in a 1024 px window", manySteps(8, [6]), { width: 640, height: 420 }],
  ])("shows all of %s, inside what the controls leave free", (_name, steps, canvas) => {
    const model = buildFlow(steps, null);
    const room = { width: canvas.width - inset.left - inset.right, height: canvas.height - inset.top - inset.bottom };
    const layout = layoutFlow(model, chooseColumns(model, room));
    const view = fitViewport(layout.bounds, canvas, inset);
    const box = shown(layout.bounds, view);
    expect(box.x).toBeGreaterThanOrEqual(inset.left - 0.01);
    expect(box.y).toBeGreaterThanOrEqual(inset.top - 0.01);
    expect(box.x + box.width).toBeLessThanOrEqual(canvas.width - inset.right + 0.01);
    expect(box.y + box.height).toBeLessThanOrEqual(canvas.height - inset.bottom + 0.01);
    // Readable: the type in a node is no smaller than three quarters of its size.
    expect(view.zoom).toBeGreaterThanOrEqual(0.75);
    expect(view.zoom).toBeLessThanOrEqual(1);
  });

  it("centres a flow that is smaller than the canvas, at its own size", () => {
    const view = fitViewport({ x: 0, y: 0, width: 200, height: 100 }, { width: 600, height: 400 }, inset);
    expect(view).toEqual({ x: 16 + (568 - 200) / 2, y: 52 + (332 - 100) / 2, zoom: 1 });
  });

  it("keeps a long flow readable on a phone: full width, from the top, the rest a scroll away", () => {
    const model = buildFlow(manySteps(9, [4]), null);
    const layout = layoutFlow(model, 1);
    const canvas = { width: 356, height: 480 };
    const view = fitViewport(layout.bounds, canvas, { top: 52, right: 12, bottom: 12, left: 12 }, { minZoom: 0.85 });
    expect(view.zoom).toBeGreaterThanOrEqual(0.85);
    const box = shown(layout.bounds, view);
    expect(box.y).toBe(52);
    expect(box.x).toBeGreaterThanOrEqual(12);
    expect(box.x + box.width).toBeLessThanOrEqual(canvas.width - 12);
    expect(box.y + box.height).toBeGreaterThan(canvas.height);
  });

  it("has a view for an empty flow", () => {
    expect(fitViewport({ x: 0, y: 0, width: 0, height: 0 }, { width: 600, height: 400 }, inset)).toEqual({
      x: 16,
      y: 52,
      zoom: 1,
    });
  });
});

describe("placeMenu", () => {
  const canvas = { width: 750, height: 520 };
  const menu = { width: 288, height: 240 };

  it("opens under the node, at its left edge", () => {
    expect(placeMenu({ x: 100, y: 80, width: 208, height: 68 }, menu, canvas)).toEqual({
      x: 100,
      y: 156,
      covers: false,
    });
  });

  it("opens above a node near the bottom", () => {
    expect(placeMenu({ x: 100, y: 400, width: 208, height: 68 }, menu, canvas)).toEqual({
      x: 100,
      y: 152,
      covers: false,
    });
  });

  it("stays whole inside the canvas beside a node at the right edge or outside the view", () => {
    expect(placeMenu({ x: 600, y: 80, width: 208, height: 68 }, menu, canvas).x).toBe(750 - 288 - 8);
    expect(placeMenu({ x: -400, y: 900, width: 208, height: 68 }, menu, canvas)).toMatchObject({
      x: 8,
      y: 520 - 240 - 8,
    });
  });

  it("covers the node rather than leave the canvas when neither side has room, and says so", () => {
    const low = { width: 356, height: 300 };
    const at = placeMenu({ x: 20, y: 120, width: 208, height: 68 }, { width: 340, height: 240 }, low);
    expect(at).toEqual({ x: 8, y: 52, covers: true });
    expect(at.y + 240).toBeLessThanOrEqual(low.height - 8);
    // With the node moved to the top of the same canvas the menu fits under it.
    expect(placeMenu({ x: 20, y: 8, width: 208, height: 34 }, { width: 340, height: 240 }, low).covers).toBe(false);
  });
});

describe("roundedPath", () => {
  it("draws a straight line as it is", () => {
    expect(roundedPath([{ x: 0, y: 10 }, { x: 44, y: 10 }])).toBe("M 0 10 L 44 10");
  });

  it("rounds each corner, and starts and ends where the line does", () => {
    const d = roundedPath(
      [
        { x: 0, y: 0 },
        { x: 20, y: 0 },
        { x: 20, y: 40 },
      ],
      8,
    );
    expect(d).toBe("M 0 0 L 12 0 Q 20 0 20 8 L 20 40");
  });

  it("makes the corner smaller where the line is short", () => {
    const d = roundedPath(
      [
        { x: 0, y: 0 },
        { x: 6, y: 0 },
        { x: 6, y: 40 },
      ],
      8,
    );
    expect(d).toBe("M 0 0 L 3 0 Q 6 0 6 3 L 6 40");
  });

  it("is empty without points", () => {
    expect(roundedPath([])).toBe("");
  });
});
