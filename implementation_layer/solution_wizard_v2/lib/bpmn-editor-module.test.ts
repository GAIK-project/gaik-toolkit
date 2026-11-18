import { describe, expect, it } from "vitest";
import { moveKeepsLanes, stepLaneChange } from "@/lib/bpmn-editor-module";
import type { BpmnMapping } from "@/lib/bpmn-canvas-ops";

// Two lanes in one pool, one above the other, as the generator draws them. Each
// lane's BPMN element lists the flow nodes in it (`flowNodeRef`).
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
const lanes = [users, ai];
// Drawn in the users lane, which lists it.
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
const label = { ...task, id: "Activity_extract_label", type: "label", labelTarget: task };
// A data object no lane lists, drawn in the users lane.
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

describe("moveKeepsLanes", () => {
  it("lets a shape move within its lane", () => {
    expect(moveKeepsLanes([task], { x: 300, y: 40 }, pool, lanes)).toBe(true);
  });

  it("allows the drag to start, before there is a delta or a target", () => {
    expect(moveKeepsLanes([task], undefined, undefined, lanes)).toBe(true);
  });

  it("refuses a move into another lane", () => {
    expect(moveKeepsLanes([task], { x: 0, y: 200 }, pool, lanes)).toBe(false);
  });

  it("refuses a move out of the lanes or onto another parent", () => {
    expect(moveKeepsLanes([task], { x: 0, y: 500 }, pool, lanes)).toBe(false);
    const root = { id: "Collaboration_1", type: "bpmn:Collaboration", x: 0, y: 0, width: 0, height: 0 };
    expect(moveKeepsLanes([task], { x: 10, y: 0 }, root, lanes)).toBe(false);
  });

  it("lets a shape drawn outside its own lane go back into it, and nowhere else", () => {
    // The review step is listed in the AI lane but drawn in the users lane (a place kept from before).
    const stray = { ...task, id: "Activity_review", businessObject: reviewBo };
    expect(moveKeepsLanes([stray], { x: 0, y: 200 }, pool, lanes)).toBe(true);
    expect(moveKeepsLanes([stray], { x: 50, y: 0 }, pool, lanes)).toBe(false);
  });

  it("keeps a shape no lane lists in the lane it is drawn in", () => {
    expect(moveKeepsLanes([data], { x: 100, y: 20 }, pool, lanes)).toBe(true);
    expect(moveKeepsLanes([data], { x: 0, y: 250 }, pool, lanes)).toBe(false);
  });

  it("refuses a label moved on its own, which the layout does not keep", () => {
    expect(moveKeepsLanes([label], { x: 10, y: 0 }, pool, lanes)).toBe(false);
  });

  it("lets a shape move freely in a drawing without lanes, within its parent", () => {
    expect(moveKeepsLanes([task], { x: 0, y: 300 }, pool, [])).toBe(true);
  });
});

describe("stepLaneChange", () => {
  const mapping: BpmnMapping = {
    Activity_extract: { kind: "automated_task", blueprint_path: "workflow.steps[0]", performed_by: "" },
    Lane_users: { kind: "lane", blueprint_path: "derived:business_spec.intended_users", participant_id: "users" },
    Lane_gaik_ai: { kind: "lane", blueprint_path: "derived:system", participant_id: "system" },
  };
  const steps = [{ id: "extract", name: "Extract" }];
  const withFlows = {
    ...task,
    incoming: [{ id: "Flow_1" }],
    outgoing: [{ id: "Flow_2" }, { id: "bad id!" }],
  } as unknown as typeof task;

  it("a step dropped into another lane is set_step_lane, and its place and flows are dropped", () => {
    expect(stepLaneChange([withFlows, label], { x: 0, y: 200 }, pool, lanes, mapping, steps)).toEqual({
      op: { op: "set_step_lane", step_id: "extract", lane_id: "system" },
      shapes: ["Activity_extract"],
      edges: ["Flow_1", "Flow_2"],
    });
  });

  it("is null within its lane, outside the lanes, for no step, for several shapes, or before a delta", () => {
    expect(stepLaneChange([task], { x: 300, y: 40 }, pool, lanes, mapping, steps)).toBeNull();
    expect(stepLaneChange([task], { x: 0, y: 900 }, pool, lanes, mapping, steps)).toBeNull();
    expect(stepLaneChange([data], { x: 0, y: 200 }, pool, lanes, mapping, steps)).toBeNull();
    expect(stepLaneChange([task, data], { x: 0, y: 200 }, pool, lanes, mapping, steps)).toBeNull();
    expect(stepLaneChange([task], undefined, pool, lanes, mapping, steps)).toBeNull();
  });

  it("is null for a lane the mapping names no participant for", () => {
    const noIds: BpmnMapping = { Activity_extract: mapping.Activity_extract };
    expect(stepLaneChange([task], { x: 0, y: 200 }, pool, lanes, noIds, steps)).toBeNull();
  });
});
