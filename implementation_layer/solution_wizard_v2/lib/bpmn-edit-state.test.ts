import { BpmnModdle } from "bpmn-moddle";
import { describe, expect, it } from "vitest";
import {
  bpmnChangeKind,
  bpmnSaveProblems,
  bpmnSemantics,
  isDeletableBpmnElement,
  isRenamableBpmnElement,
  stepIdToBpmnId,
  stepIndexForBpmnId,
  stripTaskCodePrefixes,
  type ModdleElement,
} from "./bpmn-edit-state";

// The shape of what the generator writes (solution_wizard bpmn_generator),
// cut down to what the sync reads.
function diagram({
  extractName = "[D] Data extraction",
  flows = [
    ["StartEvent_1", "Activity_ingest"],
    ["Activity_ingest", "Activity_extract"],
    ["Activity_extract", "Activity_approve"],
    ["Activity_approve", "Gateway_approve"],
    ["Gateway_approve", "EndEvent_ok"],
  ],
  extraTask = "",
  dataObjectName = "Structured JSON",
}: {
  extractName?: string;
  flows?: string[][];
  extraTask?: string;
  dataObjectName?: string;
} = {}) {
  return `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="Defs" targetNamespace="x">
  <bpmn:process id="Process_1" isExecutable="false">
    <bpmn:laneSet id="LaneSet_1"><bpmn:lane id="Lane_a" name="GenAI" /></bpmn:laneSet>
    <bpmn:startEvent id="StartEvent_1" name="Started" />
    <bpmn:userTask id="Activity_ingest" name="Invoice intake" />
    <bpmn:serviceTask id="Activity_extract" name="${extractName}" />
    <bpmn:userTask id="Activity_approve" name="Approval" />
    ${extraTask}
    <bpmn:exclusiveGateway id="Gateway_approve" name="Approved?" />
    <bpmn:endEvent id="EndEvent_ok" name="Done" />
    <bpmn:dataObjectReference id="DataObjectRef_json" name="${dataObjectName}" dataObjectRef="DataObject_json" />
    <bpmn:dataObject id="DataObject_json" />
    ${flows.map(([s, t], i) => `<bpmn:sequenceFlow id="Flow_${i}" sourceRef="${s}" targetRef="${t}" />`).join("\n    ")}
  </bpmn:process>
</bpmn:definitions>`;
}

async function semantics(xml: string) {
  const { rootElement } = await new BpmnModdle().fromXML(xml);
  return bpmnSemantics(rootElement as ModdleElement);
}

describe("stripTaskCodePrefixes", () => {
  it("leaves a name that starts with the user's own brackets whole", () => {
    for (const name of ["[Beta] Upload", "[luonnos] Tarkistus", "[Phase 2] Review", "[TOOLONG] Send"]) {
      const xml = `<bpmn:task id="a" name="${name}">`;
      expect(stripTaskCodePrefixes(xml)).toBe(xml);
    }
    expect(stripTaskCodePrefixes('<bpmn:task id="a" name="[A2S] Audio to data">')).toBe(
      '<bpmn:task id="a" name="Audio to data">',
    );
  });

  it("drops the generator's component code from task names only", () => {
    const xml = diagram();
    const stripped = stripTaskCodePrefixes(xml);
    expect(stripped).toContain('<bpmn:serviceTask id="Activity_extract" name="Data extraction" />');
    expect(stripped).toContain('name="Invoice intake"');
    expect(stripTaskCodePrefixes('<serviceTask id="a" name="[LLM] Classification">')).toBe(
      '<serviceTask id="a" name="Classification">',
    );
  });

  it("leaves other elements and names without a code alone", () => {
    const xml = '<bpmn:dataObjectReference id="d" name="[D] Draft" /><bpmn:task id="t" name="Draft [v2]" />';
    expect(stripTaskCodePrefixes(xml)).toBe(xml);
  });
});

describe("bpmnSemantics", () => {
  it("reads tasks, gateways, data objects, start events and the flows between steps", async () => {
    const sem = await semantics(diagram());
    expect(sem.tasks.map((t) => t.id)).toEqual(["Activity_approve", "Activity_extract", "Activity_ingest"]);
    expect(sem.tasks.find((t) => t.id === "Activity_extract")?.name).toBe("[D] Data extraction");
    expect(sem.gateways).toEqual([{ id: "Gateway_approve", name: "Approved?" }]);
    expect(sem.dataObjects).toEqual([{ id: "DataObjectRef_json", name: "Structured JSON" }]);
    expect(sem.startEvents).toEqual(["StartEvent_1"]);
    expect(sem.flows).toContain("Activity_ingest>Activity_extract");
  });

  it("is empty for a document without a process", () => {
    expect(bpmnSemantics(null).tasks).toEqual([]);
  });
});

describe("bpmnChangeKind", () => {
  it("tells a rename from a change to what is connected", async () => {
    const base = await semantics(diagram());
    expect(bpmnChangeKind(base, await semantics(diagram()))).toBe("none");
    expect(bpmnChangeKind(base, await semantics(diagram({ extractName: "Read the invoice" })))).toBe("rename");
    expect(bpmnChangeKind(base, await semantics(diagram({ dataObjectName: "Invoice data" })))).toBe("rename");
    const reordered = diagram({
      flows: [
        ["StartEvent_1", "Activity_extract"],
        ["Activity_extract", "Activity_ingest"],
        ["Activity_ingest", "Activity_approve"],
        ["Activity_approve", "Gateway_approve"],
        ["Gateway_approve", "EndEvent_ok"],
      ],
    });
    expect(bpmnChangeKind(base, await semantics(reordered))).toBe("structure");
    const added = diagram({ extraTask: '<bpmn:task id="Activity_new" name="Check" />' });
    expect(bpmnChangeKind(base, await semantics(added))).toBe("structure");
  });
});

describe("bpmnSaveProblems", () => {
  it("finds a task that no flow from the start reaches, and a task without a name", async () => {
    const sem = await semantics(diagram({ extraTask: '<bpmn:task id="Activity_new" />' }));
    const problems = bpmnSaveProblems(sem);
    expect(problems.unconnected.map((t) => t.id)).toEqual(["Activity_new"]);
    expect(problems.unnamed.map((t) => t.id)).toEqual(["Activity_new"]);
  });

  it("finds every step after a removed flow", async () => {
    const sem = await semantics(
      diagram({
        flows: [
          ["StartEvent_1", "Activity_ingest"],
          ["Activity_extract", "Activity_approve"],
        ],
      }),
    );
    expect(bpmnSaveProblems(sem).unconnected.map((t) => t.id)).toEqual(["Activity_approve", "Activity_extract"]);
  });

  it("reports nothing for a connected diagram", async () => {
    expect(bpmnSaveProblems(await semantics(diagram()))).toEqual({ unconnected: [], unnamed: [] });
  });
});

describe("what the canvas lets a user change", () => {
  it("renames tasks, gateways and data objects, and deletes tasks and flows only", () => {
    expect(isRenamableBpmnElement("bpmn:ServiceTask", "Activity_extract")).toBe(true);
    expect(isRenamableBpmnElement("bpmn:DataObjectReference", "DataObjectRef_json")).toBe(true);
    expect(isRenamableBpmnElement("bpmn:Lane", "Lane_a")).toBe(false);
    expect(isRenamableBpmnElement("bpmn:StartEvent", "StartEvent_1")).toBe(false);
    expect(isDeletableBpmnElement("bpmn:UserTask", "Activity_approve")).toBe(true);
    expect(isDeletableBpmnElement("bpmn:SequenceFlow", "Flow_1")).toBe(true);
    expect(isDeletableBpmnElement("bpmn:EndEvent", "EndEvent_ok")).toBe(false);
    expect(isDeletableBpmnElement("bpmn:DataObjectReference", "DataObjectRef_json")).toBe(false);
  });

  // bpmn_sync._SYNTHETIC_PREFIXES: the sync skips these, and the next diagram draws them again.
  it("leaves the generator's own tasks alone: a save would undo a rename or a delete", () => {
    for (const id of ["Activity_submit_finance_system", "Activity_generate_pdf"]) {
      expect(isRenamableBpmnElement("bpmn:ServiceTask", id)).toBe(false);
      expect(isRenamableBpmnElement("bpmn:SendTask", id)).toBe(false);
      expect(isDeletableBpmnElement("bpmn:ServiceTask", id)).toBe(false);
    }
    // A step whose id only resembles them is a step.
    expect(isRenamableBpmnElement("bpmn:ServiceTask", "Activity_generate")).toBe(true);
    expect(isDeletableBpmnElement("bpmn:UserTask", "Activity_submission")).toBe(true);
  });

  it("does not count a generated task as a step to compare or to validate", async () => {
    const withSynthetic = (name: string) =>
      diagram({
        // No flow reaches it and it has no name: neither is a problem of the user's.
        extraTask:
          `<bpmn:serviceTask id="Activity_generate_pdf" name="${name}" />` +
          '<bpmn:sendTask id="Activity_submit_finance_system" />',
      });
    const base = await semantics(withSynthetic("Generate PDF"));
    expect(base.tasks.map((t) => t.id)).toEqual(["Activity_approve", "Activity_extract", "Activity_ingest"]);
    expect(bpmnSaveProblems(base)).toEqual({ unconnected: [], unnamed: [] });
    expect(bpmnChangeKind(base, await semantics(withSynthetic("Make the PDF")))).toBe("none");
  });
});

describe("steps and diagram elements", () => {
  it("map a step to the element the generator draws for it", () => {
    expect(stepIdToBpmnId("classify")).toBe("Activity_classify");
    expect(stepIdToBpmnId("step-2.ä")).toBe("Activity_step_2_ä");
    const steps = [{ id: "ingest" }, { id: "step-2" }];
    expect(stepIndexForBpmnId(steps, "Activity_step_2")).toBe(1);
    expect(stepIndexForBpmnId(steps, "DataObjectRef_json")).toBe(-1);
    expect(stepIndexForBpmnId(steps, null)).toBe(-1);
  });
});
