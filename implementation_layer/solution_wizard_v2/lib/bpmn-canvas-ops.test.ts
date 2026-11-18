import { describe, expect, it } from "vitest";
import {
  isOperationElement,
  mappingFitsSteps,
  opForAddStep,
  opForAppend,
  opForConnection,
  opForDelete,
  opForLabelUpdate,
  opsForMove,
  stepIdOf,
  type BpmnMapping,
} from "@/lib/bpmn-canvas-ops";

// What GET /bpmn/mapping answers for the invoice process: tasks point into
// workflow.steps by index, the rest is drawn from other parts of the blueprint.
const MAPPING: BpmnMapping = {
  Activity_upload: { kind: "user_task", blueprint_path: "workflow.steps[0]" },
  Activity_extract: { kind: "automated_task", blueprint_path: "workflow.steps[1]" },
  Activity_review: { kind: "human_review", blueprint_path: "workflow.steps[2]" },
  Activity_archive: { kind: "manual_step", blueprint_path: "business_process.manual_steps[0]" },
  Gateway_approval_review: { kind: "approval_gateway", blueprint_path: "derived:approval_after:review" },
  StartEvent_1: { kind: "start_event", blueprint_path: "derived:start" },
  Lane_clerk: { kind: "lane", blueprint_path: "business_process.participants[0]" },
  DataObjectRef_invoice: { kind: "data_object", blueprint_path: "artifacts.invoice" },
};
const STEPS = [
  { id: "upload", name: "Upload" },
  { id: "extract", name: "Extract" },
  { id: "review", name: "Review" },
];

describe("stepIdOf", () => {
  it("stepIdOf finds the step behind a task", () => {
    expect(stepIdOf("Activity_extract", MAPPING, STEPS)).toBe("extract");
    expect(stepIdOf("Activity_upload", MAPPING, STEPS)).toBe("upload");
  });

  it("stepIdOf is null for a derived gateway", () => {
    expect(stepIdOf("Gateway_approval_review", MAPPING, STEPS)).toBeNull();
    expect(stepIdOf("StartEvent_1", MAPPING, STEPS)).toBeNull();
  });

  it("is null for manual steps, lanes, data objects and unknown elements", () => {
    expect(stepIdOf("Activity_archive", MAPPING, STEPS)).toBeNull();
    expect(stepIdOf("Lane_clerk", MAPPING, STEPS)).toBeNull();
    expect(stepIdOf("DataObjectRef_invoice", MAPPING, STEPS)).toBeNull();
    expect(stepIdOf("Flow_1", MAPPING, STEPS)).toBeNull();
  });

  it("is null when the index is past the steps it was given", () => {
    expect(stepIdOf("Activity_review", MAPPING, STEPS.slice(0, 2))).toBeNull();
  });

  it("does not read a path that only starts like a step", () => {
    const odd: BpmnMapping = { X: { blueprint_path: "workflow.steps[1].outputs[0]" } };
    expect(stepIdOf("X", odd, STEPS)).toBeNull();
  });
});

describe("opForLabelUpdate", () => {
  it("is rename_step with the trimmed name", () => {
    expect(opForLabelUpdate("Activity_extract", "  Read fields ", MAPPING, STEPS)).toEqual({
      op: "rename_step",
      step_id: "extract",
      name: "Read fields",
    });
  });

  it("is null for an empty or unchanged name and for a derived element", () => {
    expect(opForLabelUpdate("Activity_extract", "   ", MAPPING, STEPS)).toBeNull();
    expect(opForLabelUpdate("Activity_extract", null, MAPPING, STEPS)).toBeNull();
    expect(opForLabelUpdate("Activity_extract", "Extract", MAPPING, STEPS)).toBeNull();
    expect(opForLabelUpdate("Gateway_approval_review", "OK?", MAPPING, STEPS)).toBeNull();
  });
});

describe("opForConnection", () => {
  it("opForConnection between two steps is connect", () => {
    expect(opForConnection("Activity_upload", "Activity_review", MAPPING, STEPS)).toEqual({
      op: "connect",
      source: "upload",
      target: "review",
    });
  });

  it("is null to or from what is not a step, and from a step to itself", () => {
    expect(opForConnection("Activity_upload", "Gateway_approval_review", MAPPING, STEPS)).toBeNull();
    expect(opForConnection("DataObjectRef_invoice", "Activity_review", MAPPING, STEPS)).toBeNull();
    expect(opForConnection("Activity_upload", "Activity_upload", MAPPING, STEPS)).toBeNull();
  });
});

describe("opForDelete", () => {
  it("opForDelete of a flow is disconnect", () => {
    expect(
      opForDelete(
        { id: "Flow_2", type: "bpmn:SequenceFlow", source: "Activity_extract", target: "Activity_review" },
        MAPPING,
        STEPS,
      ),
    ).toEqual({ op: "disconnect", source: "extract", target: "review" });
  });

  it("of a step's task is remove_step", () => {
    expect(opForDelete({ id: "Activity_review", type: "bpmn:UserTask" }, MAPPING, STEPS)).toEqual({
      op: "remove_step",
      step_id: "review",
    });
  });

  it("is null for a flow through a gateway and for a derived element", () => {
    expect(
      opForDelete(
        { id: "Flow_9", type: "bpmn:SequenceFlow", source: "Activity_review", target: "Gateway_approval_review" },
        MAPPING,
        STEPS,
      ),
    ).toBeNull();
    expect(opForDelete({ id: "StartEvent_1", type: "bpmn:StartEvent" }, MAPPING, STEPS)).toBeNull();
    expect(opForDelete({ id: "Activity_archive", type: "bpmn:Task" }, MAPPING, STEPS)).toBeNull();
  });
});

describe("adding and moving steps", () => {
  it("Add step appends after the last step", () => {
    expect(opForAddStep("New step", STEPS)).toEqual({
      op: "add_step",
      name: "New step",
      type: "user_task",
      after: "review",
    });
    expect(opForAddStep("New step", [])).toEqual({ op: "add_step", name: "New step", type: "user_task" });
  });

  it("Append step adds a step after the one picked", () => {
    expect(opForAppend("Activity_upload", "New step", MAPPING, STEPS)).toEqual({
      op: "add_step",
      name: "New step",
      type: "user_task",
      after: "upload",
    });
    expect(opForAppend("StartEvent_1", "New step", MAPPING, STEPS)).toBeNull();
  });

  it("Move later puts the step after the next one", () => {
    expect(opsForMove("Activity_upload", "later", MAPPING, STEPS)).toEqual([
      { op: "move_step", step_id: "upload", after: "extract" },
    ]);
  });

  it("Move earlier puts the step after the one two before it", () => {
    expect(opsForMove("Activity_review", "earlier", MAPPING, STEPS)).toEqual([
      { op: "move_step", step_id: "review", after: "upload" },
    ]);
  });

  it("Move earlier to the start keeps the old first step after it", () => {
    expect(opsForMove("Activity_extract", "earlier", MAPPING, STEPS)).toEqual([
      { op: "move_step", step_id: "extract", after: null },
      { op: "connect", source: "extract", target: "upload" },
    ]);
  });

  it("is null for the first step earlier, the last later, and what is no step", () => {
    expect(opsForMove("Activity_upload", "earlier", MAPPING, STEPS)).toBeNull();
    expect(opsForMove("Activity_review", "later", MAPPING, STEPS)).toBeNull();
    expect(opsForMove("Gateway_approval_review", "later", MAPPING, STEPS)).toBeNull();
  });
});

describe("isOperationElement", () => {
  it("is true for a step's task and for a flow between two steps only", () => {
    expect(isOperationElement({ id: "Activity_upload", type: "bpmn:UserTask" }, MAPPING, STEPS)).toBe(true);
    expect(
      isOperationElement(
        { id: "Flow_1", type: "bpmn:SequenceFlow", source: "Activity_upload", target: "Activity_extract" },
        MAPPING,
        STEPS,
      ),
    ).toBe(true);
    expect(isOperationElement({ id: "StartEvent_1", type: "bpmn:StartEvent" }, MAPPING, STEPS)).toBe(false);
  });
});

describe("mappingFitsSteps", () => {
  it("is true when each step's task is drawn for the step at its index", () => {
    expect(mappingFitsSteps(MAPPING, STEPS)).toBe(true);
  });

  it("is false for steps of another version than the diagram's", () => {
    expect(mappingFitsSteps(MAPPING, [STEPS[1], STEPS[0], STEPS[2]])).toBe(false);
    expect(mappingFitsSteps(MAPPING, STEPS.slice(0, 2))).toBe(false);
    expect(mappingFitsSteps(MAPPING, [...STEPS, { id: "deliver" }])).toBe(false);
  });

  it("reads a decision step drawn as a gateway and an id with other characters", () => {
    const mapping: BpmnMapping = {
      "Activity_read_mail": { blueprint_path: "workflow.steps[0]" },
      Gateway_route: { blueprint_path: "workflow.steps[1]" },
    };
    expect(mappingFitsSteps(mapping, [{ id: "read-mail" }, { id: "route" }])).toBe(true);
  });
});
