import { describe, expect, it } from "vitest";
import {
  dataObjectOf,
  holdsData,
  opForDataObjectRename,
  exceptionOf,
  opForRework,
  reworkProblem,
  reworkTargets,
  decisionOf,
  decisionProblem,
  isDecisionStep,
  opForDecision,
  stepHasDecision,
  isOperationElement,
  laneIdOf,
  mappingFitsSteps,
  opForLaneRename,
  opForStepLane,
  performedByOf,
  opForAddStep,
  opForAppend,
  opForConnection,
  opForDelete,
  opForDeleteKey,
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

describe("opForDeleteKey", () => {
  const path = { id: "wrong_class", name: "Wrong", attached_to: "review", condition: "c", outcome: "loop_to:extract" };
  const mapping: BpmnMapping = {
    ...MAPPING,
    Gateway_approval_review: { kind: "approval_gateway", blueprint_path: "derived:approval_after:review", exception: path },
    Gateway_exc_wrong_class: { kind: "exception_gateway", blueprint_path: "business_process.exceptions[0]", exception: path },
  };
  const steps = [{ id: "upload" }, { id: "extract" }, { id: "review" }];

  it("does nothing on the approval gateway, whose pad's Remove still removes its path", () => {
    const gateway = { id: "Gateway_approval_review", type: "bpmn:ExclusiveGateway" };
    expect(opForDeleteKey(gateway, mapping, steps)).toBeNull();
    expect(opForDelete(gateway, mapping, steps)).toEqual({ op: "remove_rework_path", exception_id: "wrong_class" });
  });

  it("removes what the pad's Remove removes everywhere else", () => {
    const pathGateway = { id: "Gateway_exc_wrong_class", type: "bpmn:ExclusiveGateway" };
    expect(opForDeleteKey(pathGateway, mapping, steps)).toEqual({
      op: "remove_rework_path",
      exception_id: "wrong_class",
    });
    expect(opForDeleteKey({ id: "Activity_extract", type: "bpmn:ServiceTask" }, mapping, steps)).toEqual({
      op: "remove_step",
      step_id: "extract",
    });
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

describe("isDecisionStep", () => {
  // A decision is a workflow step too, drawn as a gateway (bpmn_generator `_map(nid, step.type, ...)`).
  const withDecision: BpmnMapping = {
    ...MAPPING,
    Gateway_approve: { kind: "decision", blueprint_path: "workflow.steps[3]" },
  };
  const steps = [...STEPS, { id: "approve", name: "Approved?" }];

  it("is true for a decision step's gateway, which stepIdOf still resolves", () => {
    expect(stepIdOf("Gateway_approve", withDecision, steps)).toBe("approve");
    expect(isDecisionStep("Gateway_approve", withDecision)).toBe(true);
  });

  it("is false for tasks, derived gateways and unknown elements", () => {
    expect(isDecisionStep("Activity_extract", withDecision)).toBe(false);
    expect(isDecisionStep("Gateway_approval_review", withDecision)).toBe(false);
    expect(isDecisionStep("nope", withDecision)).toBe(false);
  });
});

describe("lanes", () => {
  // The mapping names each lane's participant and each step's performed_by.
  const withLanes: BpmnMapping = {
    ...MAPPING,
    Activity_upload: { kind: "user_task", blueprint_path: "workflow.steps[0]", performed_by: "" },
    Activity_review: { kind: "human_review", blueprint_path: "workflow.steps[2]", performed_by: "legal" },
    Lane_clerk: { kind: "lane", blueprint_path: "business_process.participants[0]", participant_id: "clerk" },
    Lane_gaik_ai: { kind: "lane", blueprint_path: "derived:system", participant_id: "system" },
    Lane_legal: { kind: "lane", blueprint_path: "business_process.participants[1]", participant_id: "legal" },
  };

  it("laneIdOf is the lane's participant id, null for anything else", () => {
    expect(laneIdOf("Lane_clerk", withLanes)).toBe("clerk");
    expect(laneIdOf("Lane_gaik_ai", withLanes)).toBe("system");
    expect(laneIdOf("Lane_clerk", MAPPING)).toBeNull();
    expect(laneIdOf("Activity_upload", withLanes)).toBeNull();
    expect(laneIdOf("nope", withLanes)).toBeNull();
  });

  it("performedByOf is the step's performed_by, empty for the lane of its type", () => {
    expect(performedByOf("Activity_review", withLanes)).toBe("legal");
    expect(performedByOf("Activity_upload", withLanes)).toBe("");
    expect(performedByOf("Activity_extract", withLanes)).toBe("");
  });

  it("a step dropped in a lane is set_step_lane; nothing for a lane it is in or no step", () => {
    expect(opForStepLane("Activity_upload", "Lane_legal", "Lane_clerk", withLanes, STEPS)).toEqual({
      op: "set_step_lane",
      step_id: "upload",
      lane_id: "legal",
    });
    expect(opForStepLane("Activity_upload", "Lane_clerk", "Lane_clerk", withLanes, STEPS)).toBeNull();
    expect(opForStepLane("Activity_archive", "Lane_legal", "Lane_clerk", withLanes, STEPS)).toBeNull();
    expect(opForStepLane("Activity_upload", "Lane_unknown", "Lane_clerk", withLanes, STEPS)).toBeNull();
  });

  it("a lane renamed in place is rename_lane; nothing for an empty or unchanged name", () => {
    expect(opForLaneRename("Lane_legal", " Legal team ", "Legal", withLanes)).toEqual({
      op: "rename_lane",
      lane_id: "legal",
      name: "Legal team",
    });
    expect(opForLaneRename("Lane_legal", "Legal", "Legal", withLanes)).toBeNull();
    expect(opForLaneRename("Lane_legal", "  ", "Legal", withLanes)).toBeNull();
    expect(opForLaneRename("Activity_upload", "X", "Upload", withLanes)).toBeNull();
  });
});

describe("business decisions", () => {
  const decision = {
    id: "big",
    name: "Big?",
    after: "extract",
    branches: [
      { condition: "Yes", target: "review" },
      { condition: "No", target: "end" },
    ],
  };
  const withDecision: BpmnMapping = {
    ...MAPPING,
    Gateway_decision_big: { kind: "decision_point", blueprint_path: "business_process.decision_points[0]", decision },
  };

  it("names the decision behind a decision_point gateway, and nothing else", () => {
    expect(decisionOf("Gateway_decision_big", withDecision)).toEqual(decision);
    expect(decisionOf("Gateway_approval_review", withDecision)).toBeNull();
    expect(decisionOf("Activity_extract", withDecision)).toBeNull();
    // A decision_point entry without its decision (an older wizard_api) gives no tools.
    const bare: BpmnMapping = { X: { kind: "decision_point", blueprint_path: "business_process.decision_points[0]" } };
    expect(decisionOf("X", bare)).toBeNull();
  });

  it("says which step a decision already follows", () => {
    expect(stepHasDecision("extract", withDecision)).toBe(true);
    expect(stepHasDecision("upload", withDecision)).toBe(false);
  });

  it("deletes a decision with remove_decision, and it is an operation element; a derived gateway is not", () => {
    expect(opForDelete({ id: "Gateway_decision_big", type: "bpmn:ExclusiveGateway" }, withDecision, STEPS)).toEqual({
      op: "remove_decision",
      decision_id: "big",
    });
    expect(isOperationElement({ id: "Gateway_decision_big", type: "bpmn:ExclusiveGateway" }, withDecision, STEPS)).toBe(true);
    expect(isOperationElement({ id: "Gateway_approval_review", type: "bpmn:ExclusiveGateway" }, withDecision, STEPS)).toBe(
      false,
    );
  });

  it("checks the dialog's values: a name, 2 to 5 branches with conditions, not all to one place", () => {
    const ok = { name: " Big? ", branches: decision.branches };
    expect(decisionProblem(ok)).toBeNull();
    expect(decisionProblem({ ...ok, name: "  " })).toBe("name");
    expect(decisionProblem({ ...ok, branches: [decision.branches[0]] })).toBe("count");
    expect(decisionProblem({ ...ok, branches: Array(6).fill(decision.branches[0]) })).toBe("count");
    expect(decisionProblem({ ...ok, branches: [{ condition: " ", target: "end" }, decision.branches[0]] })).toBe("condition");
    expect(decisionProblem({ ...ok, branches: [{ condition: "x", target: "" }, decision.branches[0]] })).toBe("target");
    expect(
      decisionProblem({
        ...ok,
        branches: [
          { condition: "a", target: "end" },
          { condition: "b", target: "end" },
        ],
      }),
    ).toBe("same_target");
  });

  it("makes add_decision after a step, and update_decision for a decision, trimmed", () => {
    const values = { name: " Big? ", branches: [{ condition: " Yes ", target: "review" }, decision.branches[1]] };
    expect(opForDecision(values, { after: "extract" })).toEqual({
      op: "add_decision",
      after: "extract",
      name: "Big?",
      branches: [
        { condition: "Yes", target: "review" },
        { condition: "No", target: "end" },
      ],
    });
    expect(opForDecision({ ...values, name: "" }, { after: "extract" })).toBeNull();
  });

  it("sends only what an edit changed: an agent's branches (a branch back among them) stay untouched by a rename", () => {
    const agents = {
      ...decision,
      branches: [
        { condition: "ok", target: "review" },
        { condition: "again", target: "upload" },
      ],
    };
    const same = { name: agents.name, branches: agents.branches };
    // Nothing changed (the same text around blanks): nothing to send.
    expect(opForDecision({ ...same, name: " Big? " }, { decision: agents })).toBeNull();
    expect(opForDecision({ ...same, name: "Bigger?" }, { decision: agents })).toEqual({
      op: "update_decision",
      decision_id: "big",
      name: "Bigger?",
    });
    const branches = [agents.branches[0], { condition: "redo", target: "upload" }];
    expect(opForDecision({ ...same, branches }, { decision: agents })).toEqual({
      op: "update_decision",
      decision_id: "big",
      branches,
    });
    expect(opForDecision({ name: "B", branches }, { decision: agents })).toEqual({
      op: "update_decision",
      decision_id: "big",
      name: "B",
      branches,
    });
  });
});

describe("rework and rejection paths", () => {
  const rework = {
    id: "fields_wrong",
    name: "Fields wrong",
    attached_to: "review",
    condition: "Wrong",
    outcome: "loop_to:extract",
  };
  const rejection = { id: "unreadable", name: "Unreadable", attached_to: "extract", condition: "", outcome: "end" };
  const withPaths: BpmnMapping = {
    ...MAPPING,
    Gateway_approval_review: { ...MAPPING.Gateway_approval_review, exception: rework },
    Gateway_exc_unreadable: { kind: "exception_gateway", blueprint_path: "business_process.exceptions[1]", exception: rejection },
    EndEvent_unreadable: { kind: "end_event", blueprint_path: "business_process.exceptions[1]", exception: rejection },
  };

  it("names the path behind its elements, and nothing else", () => {
    expect(exceptionOf("Gateway_exc_unreadable", withPaths)).toEqual(rejection);
    expect(exceptionOf("EndEvent_unreadable", withPaths)).toEqual(rejection);
    expect(exceptionOf("Gateway_approval_review", withPaths)).toEqual(rework);
    expect(exceptionOf("Gateway_approval_review", MAPPING)).toBeNull();
    expect(exceptionOf("Activity_review", withPaths)).toBeNull();
    expect(exceptionOf("toString", withPaths)).toBeNull();
    // An entry without its path (an older wizard_api) gives no tools.
    const bare: BpmnMapping = { X: { kind: "exception_gateway", blueprint_path: "business_process.exceptions[0]" } };
    expect(exceptionOf("X", bare)).toBeNull();
  });

  it("deletes a path with remove_rework_path, and its elements are operation elements", () => {
    expect(opForDelete({ id: "EndEvent_unreadable", type: "bpmn:EndEvent" }, withPaths, STEPS)).toEqual({
      op: "remove_rework_path",
      exception_id: "unreadable",
    });
    expect(isOperationElement({ id: "Gateway_exc_unreadable", type: "bpmn:ExclusiveGateway" }, withPaths, STEPS)).toBe(true);
    expect(isOperationElement({ id: "Gateway_approval_review", type: "bpmn:ExclusiveGateway" }, withPaths, STEPS)).toBe(true);
    expect(isOperationElement({ id: "Gateway_approval_review", type: "bpmn:ExclusiveGateway" }, MAPPING, STEPS)).toBe(false);
  });

  it("offers the steps up to the path's own as targets", () => {
    expect(reworkTargets("extract", STEPS).map((s) => s.id)).toEqual(["upload", "extract"]);
    expect(reworkTargets("review", STEPS).map((s) => s.id)).toEqual(["upload", "extract", "review"]);
    // A path on a manual step (after every workflow step in the drawing): all of them.
    expect(reworkTargets("archive", STEPS).map((s) => s.id)).toEqual(["upload", "extract", "review"]);
  });

  it("checks the dialog's values: a name and an outcome", () => {
    const ok = { name: " Redo ", condition: "", outcome: "loop_to:upload" };
    expect(reworkProblem(ok)).toBeNull();
    expect(reworkProblem({ ...ok, outcome: "end" })).toBeNull();
    expect(reworkProblem({ ...ok, name: "  " })).toBe("name");
    expect(reworkProblem({ ...ok, outcome: "" })).toBe("outcome");
  });

  it("makes add_rework_path on a step, trimmed; null while the values are no path", () => {
    expect(opForRework({ name: " Redo ", condition: " Wrong ", outcome: "loop_to:upload" }, { attachedTo: "extract" })).toEqual({
      op: "add_rework_path",
      attached_to: "extract",
      name: "Redo",
      condition: "Wrong",
      outcome: "loop_to:upload",
    });
    expect(opForRework({ name: "", condition: "", outcome: "end" }, { attachedTo: "extract" })).toBeNull();
  });

  it("sends only what an edit changed, and nothing when nothing did", () => {
    const same = { name: rework.name, condition: rework.condition, outcome: rework.outcome };
    expect(opForRework({ ...same, name: " Fields wrong " }, { exception: rework })).toBeNull();
    expect(opForRework({ ...same, name: "Redo" }, { exception: rework })).toEqual({
      op: "update_rework_path",
      exception_id: "fields_wrong",
      name: "Redo",
    });
    expect(opForRework({ ...same, condition: "", outcome: "end" }, { exception: rework })).toEqual({
      op: "update_rework_path",
      exception_id: "fields_wrong",
      condition: "",
      outcome: "end",
    });
  });
});

describe("data objects", () => {
  // The mapping names a drawn data object's artifact and its label ("" when the generator names it).
  const DATA: BpmnMapping = {
    ...MAPPING,
    DataObjectRef_invoice: {
      kind: "data_object",
      blueprint_path: "artifacts.invoice",
      data_object: { id: "invoice", label: "" },
    },
    DataObjectRef_fields: {
      kind: "data_object",
      blueprint_path: "artifacts.fields",
      data_object: { id: "fields", label: "Invoice fields" },
    },
    DataStoreRef_erp: { kind: "data_store", blueprint_path: "technical_spec.integration_targets[0]" },
  };

  it("dataObjectOf names the artifact behind a data object, and nothing else", () => {
    expect(dataObjectOf("DataObjectRef_fields", DATA)).toEqual({ id: "fields", label: "Invoice fields" });
    expect(dataObjectOf("DataStoreRef_erp", DATA)).toBeNull();
    expect(dataObjectOf("Activity_extract", DATA)).toBeNull();
    // A mapping without the artifact (an older wizard_api): no data tools.
    expect(dataObjectOf("DataObjectRef_invoice", MAPPING)).toBeNull();
  });

  it("a typed name is rename_data_object; an emptied one clears the label", () => {
    expect(opForDataObjectRename("DataObjectRef_fields", " Fields read ", "Invoice fields", DATA)).toEqual({
      op: "rename_data_object",
      artifact_id: "fields",
      label: "Fields read",
    });
    expect(opForDataObjectRename("DataObjectRef_fields", "  ", "Invoice fields", DATA)).toEqual({
      op: "rename_data_object",
      artifact_id: "fields",
      label: "",
    });
    expect(opForDataObjectRename("DataObjectRef_invoice", "Scanned invoice", "Invoice", DATA)).toEqual({
      op: "rename_data_object",
      artifact_id: "invoice",
      label: "Scanned invoice",
    });
  });

  it("is null for an unchanged name, an emptied generated name and what is no data object", () => {
    expect(opForDataObjectRename("DataObjectRef_fields", "Invoice fields", "Invoice fields", DATA)).toBeNull();
    // No label of its own: the generated name kept, or emptied, changes nothing.
    expect(opForDataObjectRename("DataObjectRef_invoice", "Invoice", "Invoice", DATA)).toBeNull();
    expect(opForDataObjectRename("DataObjectRef_invoice", "", "Invoice", DATA)).toBeNull();
    expect(opForDataObjectRename("DataStoreRef_erp", "ERP", "Store", DATA)).toBeNull();
    expect(opForDataObjectRename("Activity_extract", "X", "Extract", DATA)).toBeNull();
  });

  it("a line from a data object to a step is an input, from a step to a data object an output", () => {
    expect(opForConnection("DataObjectRef_invoice", "Activity_review", DATA, STEPS)).toEqual({
      op: "link_data",
      artifact_id: "invoice",
      step_id: "review",
      role: "input",
    });
    expect(opForConnection("Activity_extract", "DataObjectRef_fields", DATA, STEPS)).toEqual({
      op: "link_data",
      artifact_id: "fields",
      step_id: "extract",
      role: "output",
    });
    expect(opForConnection("DataObjectRef_invoice", "DataObjectRef_fields", DATA, STEPS)).toBeNull();
    expect(opForConnection("DataStoreRef_erp", "Activity_review", DATA, STEPS)).toBeNull();
    expect(opForConnection("DataObjectRef_invoice", "Activity_archive", DATA, STEPS)).toBeNull();
  });

  it("deleting a data association is unlink_data, with the role from its kind", () => {
    const input = { id: "DataAssoc_1", type: "bpmn:DataInputAssociation", source: "DataObjectRef_invoice", target: "Activity_extract" };
    const output = { id: "DataAssoc_2", type: "bpmn:DataOutputAssociation", source: "Activity_extract", target: "DataObjectRef_fields" };
    expect(opForDelete(input, DATA, STEPS)).toEqual({
      op: "unlink_data",
      artifact_id: "invoice",
      step_id: "extract",
      role: "input",
    });
    expect(opForDelete(output, DATA, STEPS)).toEqual({
      op: "unlink_data",
      artifact_id: "fields",
      step_id: "extract",
      role: "output",
    });
    expect(isOperationElement(input, DATA, STEPS)).toBe(true);
    // A data store's association stays as it is.
    const store = { id: "DataAssoc_3", type: "bpmn:DataOutputAssociation", source: "Activity_extract", target: "DataStoreRef_erp" };
    expect(opForDelete(store, DATA, STEPS)).toBeNull();
    expect(isOperationElement(store, DATA, STEPS)).toBe(false);
  });

  it("a data object has tools but no Delete of its own", () => {
    expect(isOperationElement({ id: "DataObjectRef_fields", type: "bpmn:DataObjectReference" }, DATA, STEPS)).toBe(true);
    expect(opForDelete({ id: "DataObjectRef_fields", type: "bpmn:DataObjectReference" }, DATA, STEPS)).toBeNull();
    expect(isOperationElement({ id: "DataStoreRef_erp", type: "bpmn:DataStoreReference" }, DATA, STEPS)).toBe(false);
  });
});

describe("holdsData", () => {
  it("is true for the tasks a step is drawn as, false for a gateway and anything else", () => {
    for (const type of ["bpmn:Task", "bpmn:UserTask", "bpmn:ServiceTask"]) expect(holdsData(type), type).toBe(true);
    for (const type of ["bpmn:ExclusiveGateway", "bpmn:StartEvent", "bpmn:DataObjectReference", "bpmn:Lane"]) {
      expect(holdsData(type), type).toBe(false);
    }
  });
});
