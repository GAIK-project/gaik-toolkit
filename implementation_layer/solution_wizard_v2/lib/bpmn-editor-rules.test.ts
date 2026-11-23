import EventBus from "diagram-js/lib/core/EventBus";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { gaikEditorModule } from "@/lib/bpmn-editor-module";
import type { BpmnMapping } from "@/lib/bpmn-canvas-ops";

// GaikRules and GaikOperations, with a stub context: no canvas is drawn.
//
// Both are built by bpmn-js's injector, which names their services in `$inject`;
// here they get a real diagram-js event bus and plain objects for the rest.
// The palette, the context pad and the menus are covered by the e2e specs.

type Built = new (...args: unknown[]) => unknown;
const classOf = (entry: unknown): Built => (entry as [string, Built])[1];

const extractBo = { id: "Activity_extract" };
const reviewBo = { id: "Activity_review" };
const pool = { id: "Participant_main", type: "bpmn:Participant", x: 0, y: 0, width: 1000, height: 400 };
const users = {
  id: "Lane_users",
  type: "bpmn:Lane",
  x: 30,
  y: 0,
  width: 970,
  height: 200,
  parent: pool,
  businessObject: { flowNodeRef: [extractBo] },
};
const ai = {
  id: "Lane_gaik_ai",
  type: "bpmn:Lane",
  x: 30,
  y: 200,
  width: 970,
  height: 200,
  parent: pool,
  businessObject: { flowNodeRef: [reviewBo] },
};
const task = {
  id: "Activity_extract",
  type: "bpmn:Task",
  x: 100,
  y: 60,
  width: 100,
  height: 80,
  parent: pool,
  businessObject: extractBo,
};
const reviewTask = { ...task, id: "Activity_review", businessObject: reviewBo, x: 300 };
const approval = { ...task, id: "Gateway_approve", type: "bpmn:ExclusiveGateway" };
const generated = { ...task, id: "Activity_submit_finance", type: "bpmn:SendTask" };
const data = {
  id: "DataObjectReference_fields",
  type: "bpmn:DataObjectReference",
  x: 300,
  y: 20,
  width: 36,
  height: 50,
  parent: pool,
  businessObject: { id: "DataObjectReference_fields" },
};

const mapping: BpmnMapping = {
  Activity_extract: { kind: "automated_task", blueprint_path: "workflow.steps[0]", performed_by: "" },
  Activity_review: { kind: "user_task", blueprint_path: "workflow.steps[1]", performed_by: "" },
  Gateway_approve: { kind: "approval_gateway", blueprint_path: "derived:approval" },
  DataObjectReference_fields: {
    kind: "data_object",
    blueprint_path: "artifacts[0]",
    data_object: { id: "fields", label: "Fields" },
  },
  Lane_users: { kind: "lane", blueprint_path: "derived:business_spec.intended_users", participant_id: "users" },
  Lane_gaik_ai: { kind: "lane", blueprint_path: "derived:system", participant_id: "system" },
};
const steps = [
  { id: "extract", name: "Extract" },
  { id: "review", name: "Review" },
];
const live = { mapping, steps };
const everything = [task, reviewTask, approval, generated, data, users, ai, pool];

describe("GaikRules", () => {
  function rulesFor(context: typeof live | null) {
    const bus = new EventBus();
    const config = { ops: context ? { context: () => context } : undefined, labels: {} };
    new (classOf(gaikEditorModule.gaikRules))(bus, config, { getAll: () => everything });
    // What bpmn-js's rules ask: undefined is no objection, false a refusal.
    return (action: string, ruleContext: Record<string, unknown>) =>
      bus.fire(`commandStack.${action}.canExecute`, { command: action, context: ruleContext });
  }

  it("lets one step be deleted from the keyboard, and nothing else", () => {
    const rules = rulesFor(live);
    expect(rules("elements.delete", { elements: [task] })).toEqual([task]);
    expect(rules("elements.delete", { elements: [task, reviewTask] })).toBe(false);
    // A gateway the generator draws, a task it draws by itself and a data object have no Delete.
    expect(rules("elements.delete", { elements: [approval] })).toBe(false);
    expect(rules("elements.delete", { elements: [generated] })).toBe(false);
    expect(rules("elements.delete", { elements: [data] })).toBe(false);
  });

  it("allows nothing on a canvas that is read-only or locked (no operations context)", () => {
    const rules = rulesFor(null);
    expect(rules("elements.delete", { elements: [task] })).toBe(false);
    expect(rules("connection.start", { source: task })).toBe(false);
    expect(rules("connection.create", { source: task, target: reviewTask })).toBe(false);
    expect(rules("elements.move", { shapes: [task], delta: { x: 10, y: 0 }, target: pool })).toBe(false);
    expect(rules("connection.updateWaypoints", { connection: { id: "Flow_1" } })).toBe(false);
  });

  it("never creates, resizes, copies, attaches or reconnects", () => {
    const rules = rulesFor(live);
    for (const action of ["shape.resize", "shape.create", "elements.create", "elements.paste", "element.copy"]) {
      expect(rules(action, {})).toBe(false);
    }
    expect(rules("shape.attach", {})).toBe(false);
    expect(rules("connection.reconnect", {})).toBe(false);
  });

  it("starts a line only at a step or a data object, and ends it at a step, or a task for a data object", () => {
    const rules = rulesFor(live);
    expect(rules("connection.start", { source: task })).toBeUndefined();
    expect(rules("connection.start", { source: data })).toBeUndefined();
    expect(rules("connection.start", { source: generated })).toBe(false);
    expect(rules("connection.create", { source: task, target: reviewTask })).toBeUndefined();
    expect(rules("connection.create", { source: task, target: task })).toBe(false);
    expect(rules("connection.create", { source: data, target: task })).toBeUndefined();
    expect(rules("connection.create", { source: task, target: data })).toBeUndefined();
    expect(rules("connection.create", { source: data, target: generated })).toBe(false);
    expect(rules("connection.create", { source: data, target: data })).toBe(false);
  });

  it("lets a step move within its lane, and into another lane only as a lane change", () => {
    const rules = rulesFor(live);
    expect(rules("elements.move", { shapes: [task], delta: { x: 300, y: 40 }, target: pool })).toBeUndefined();
    expect(rules("elements.move", { shapes: [task], delta: { x: 0, y: 200 }, target: pool })).toBeUndefined();
    // A lane stays where the drawing puts it; a data object may not leave its lane.
    expect(rules("elements.move", { shapes: [users], delta: { x: 0, y: 10 }, target: pool })).toBe(false);
    expect(rules("elements.move", { shapes: [data], delta: { x: 0, y: 250 }, target: pool })).toBe(false);
  });

  it("moves bends only of the flows the layout keeps", () => {
    const rules = rulesFor(live);
    expect(rules("connection.updateWaypoints", { connection: { id: "Flow_1" } })).toBeUndefined();
    expect(rules("connection.updateWaypoints", { connection: { id: "bad id!" } })).toBe(false);
  });
});

describe("GaikOperations", () => {
  const ops = {
    context: () => live,
    onOperation: vi.fn(),
    onRevert: vi.fn(),
    onLayout: vi.fn(),
    onStepLane: vi.fn(),
    refreshOps: vi.fn(),
  };
  let bus: EventBus;
  const keyboard = {
    isCmd: (e: { ctrlKey?: boolean }) => Boolean(e.ctrlKey),
    isKey: (keys: string[], e: { key: string }) => keys.includes(e.key),
  };

  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("window", { setTimeout: globalThis.setTimeout });
    for (const fn of [ops.onOperation, ops.onRevert, ops.onLayout, ops.onStepLane, ops.refreshOps]) fn.mockClear();
    bus = new EventBus();
    new (classOf(gaikEditorModule.gaikOperations))(
      bus,
      { ops, labels: { derived: "" } },
      { getAll: () => everything, getGraphics: () => null },
      keyboard,
      { close: vi.fn() },
    );
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  /** One finished command, as bpmn-js reports it: the top command, and the ones that ran inside it. */
  function finish(
    command: string,
    context: Record<string, unknown>,
    inside: [string, Record<string, unknown>][] = [],
    trigger = "execute",
  ) {
    bus.fire("commandStack.preExecute", { command, context });
    for (const [inner, innerContext] of inside) {
      bus.fire("commandStack.preExecute", { command: inner, context: innerContext });
      bus.fire("commandStack.postExecuted", {});
    }
    bus.fire("commandStack.postExecuted", {});
    bus.fire("commandStack.changed", { trigger });
    vi.runAllTimers();
  }

  it("turns a rename in place into rename_step", () => {
    finish("element.updateLabel", { element: task, newLabel: "Read the invoice", oldLabel: "Extract" });

    expect(ops.onOperation).toHaveBeenCalledWith([{ op: "rename_step", step_id: "extract", name: "Read the invoice" }]);
    expect(ops.onRevert).not.toHaveBeenCalled();
  });

  it("sends no operation for a rename that changes nothing, and puts the diagram back", () => {
    finish("element.updateLabel", { element: task, newLabel: "Extract", oldLabel: "Extract" });

    expect(ops.onOperation).not.toHaveBeenCalled();
    expect(ops.onRevert).toHaveBeenCalledTimes(1);
  });

  it("turns a line drawn between two steps into one operation, and a line with no end into a revert", () => {
    finish("connection.create", { source: task, target: reviewTask });
    expect(ops.onOperation).toHaveBeenCalledTimes(1);
    expect(ops.onRevert).not.toHaveBeenCalled();

    finish("connection.create", { source: task });
    expect(ops.onRevert).toHaveBeenCalledTimes(1);
  });

  it("turns Delete on a step into remove_step, and a delete of several things into a revert", () => {
    finish("elements.delete", { elements: [task] });
    expect(ops.onOperation).toHaveBeenCalledWith([{ op: "remove_step", step_id: "extract" }]);

    finish("elements.delete", { elements: [task, reviewTask] });
    expect(ops.onRevert).toHaveBeenCalledTimes(1);
  });

  it("keeps a move within the lane as a layout with rounded places, and sends no operation", () => {
    const moved = { ...task, x: 120.4, y: 80.6 };
    finish("elements.move", { shapes: [moved], delta: { x: 20, y: 20 } }, [["shape.move", { shape: moved }]]);

    expect(ops.onLayout).toHaveBeenCalledWith({ shapes: { Activity_extract: { x: 120, y: 81 } }, edges: {} });
    expect(ops.onOperation).not.toHaveBeenCalled();
    expect(ops.onRevert).not.toHaveBeenCalled();
  });

  it("reads a step dragged into another lane as a lane change, not a layout", () => {
    finish("elements.move", { shapes: [task], delta: { x: 0, y: 200 } }, [["shape.move", { shape: task }]]);

    expect(ops.onStepLane).toHaveBeenCalledTimes(1);
    expect(ops.onLayout).not.toHaveBeenCalled();
  });

  it("puts the server's diagram back for a change no operation describes", () => {
    finish("shape.create", { shape: task }, [["elements.create", {}]]);

    expect(ops.onRevert).toHaveBeenCalledTimes(1);
    expect(ops.onOperation).not.toHaveBeenCalled();
    expect(ops.onLayout).not.toHaveBeenCalled();
  });

  it("sends nothing for a command that was undone or redone", () => {
    finish("element.updateLabel", { element: task, newLabel: "X" }, [], "undo");

    expect(ops.onOperation).not.toHaveBeenCalled();
    expect(ops.onRevert).not.toHaveBeenCalled();
  });

  it("keeps the local undo and redo off: Ctrl+Z and Ctrl+Y are swallowed, other keys are not", () => {
    const pressed = (key: string, ctrlKey: boolean) =>
      bus.fire("keyboard.keydown", { keyEvent: { key, ctrlKey } as unknown as KeyboardEvent });
    expect(pressed("z", true)).toBe(true);
    expect(pressed("Y", true)).toBe(true);
    expect(pressed("z", false)).toBeUndefined();
    expect(pressed("a", true)).toBeUndefined();
  });

  it("opens rename in place only for a step, a lane or a data object", () => {
    const allowed = (element: unknown) => bus.fire("directEditing.activate.allowed", { element });
    expect(allowed(task)).toBeUndefined();
    expect(allowed(data)).toBeUndefined();
    expect(allowed(users)).toBeUndefined();
    expect(allowed(generated)).toBe(false);
    expect(allowed(approval)).toBe(false);
  });
});
