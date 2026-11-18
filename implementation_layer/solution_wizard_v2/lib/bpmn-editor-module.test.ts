import { describe, expect, it } from "vitest";
import { moveKeepsLanes } from "@/lib/bpmn-editor-module";

// Two lanes in one pool, one above the other, as the generator draws them.
const pool = { id: "Participant_main", type: "bpmn:Participant", x: 0, y: 0, width: 1000, height: 400 };
const users = { id: "Lane_users", type: "bpmn:Lane", x: 30, y: 0, width: 970, height: 200, parent: pool };
const ai = { id: "Lane_gaik_ai", type: "bpmn:Lane", x: 30, y: 200, width: 970, height: 200, parent: pool };
const lanes = [users, ai];
const task = { id: "Activity_extract", type: "bpmn:Task", x: 100, y: 60, width: 100, height: 80, parent: pool };
const label = { ...task, id: "Activity_extract_label", type: "label", labelTarget: task };

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

  it("refuses a label moved on its own, which the layout does not keep", () => {
    expect(moveKeepsLanes([label], { x: 10, y: 0 }, pool, lanes)).toBe(false);
  });

  it("lets a shape move freely in a drawing without lanes, within its parent", () => {
    expect(moveKeepsLanes([task], { x: 0, y: 300 }, pool, [])).toBe(true);
  });
});
