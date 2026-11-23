/**
 * What a canvas edit changes in the blueprint, read from the BPMN model.
 *
 * A save sends the whole diagram to /bpmn/sync (solution_wizard bpmn_sync),
 * which keeps task names, the order of the tasks along the sequence flows,
 * added and deleted tasks, data-object labels and gateways; the diagram is
 * then generated again from the blueprint, so positions, lanes, pools and
 * events are not kept. These helpers compare two models by what the sync
 * keeps, so moving a shape is not an unsaved change, and they find what a
 * save would lose: a task that no flow from the start reaches is dropped by
 * the sync, and a task without a name gets its id as its name.
 */

/** Task elements the sync turns into blueprint steps (bpmn_sync.TASK_TAGS). */
export const BPMN_TASK_TYPES = new Set([
  "bpmn:Task",
  "bpmn:UserTask",
  "bpmn:ServiceTask",
  "bpmn:ManualTask",
  "bpmn:SendTask",
  "bpmn:CallActivity",
]);

const GATEWAY_TYPES = new Set(["bpmn:ExclusiveGateway", "bpmn:ParallelGateway"]);
const FLOW_NODE_TYPES = new Set([
  ...BPMN_TASK_TYPES,
  ...GATEWAY_TYPES,
  "bpmn:StartEvent",
  "bpmn:EndEvent",
]);

/**
 * Tasks the generator draws by itself (sending the result on, making the
 * PDF): the sync does not read them as steps (bpmn_sync._SYNTHETIC_PREFIXES),
 * and the next diagram has them again as generated, whatever the canvas did
 * to them.
 */
const SYNTHETIC_TASK_PREFIXES = ["Activity_submit_", "Activity_generate_pdf"];

export function isSyntheticBpmnTask(id: string | null | undefined): boolean {
  return Boolean(id) && SYNTHETIC_TASK_PREFIXES.some((prefix) => id!.startsWith(prefix));
}

/** A task the sync turns into a blueprint step. */
export function isStepBpmnTask(type: string, id: string | null | undefined): boolean {
  return BPMN_TASK_TYPES.has(type) && !isSyntheticBpmnTask(id);
}

/** Elements whose name a save keeps, so the canvas lets the user rename them. */
export function isRenamableBpmnElement(type: string, id: string | null | undefined): boolean {
  return isStepBpmnTask(type, id) || GATEWAY_TYPES.has(type) || type === "bpmn:DataObjectReference";
}

/** Elements whose removal a save keeps: the steps' tasks, and the flows between steps. */
export function isDeletableBpmnElement(type: string, id: string | null | undefined): boolean {
  return isStepBpmnTask(type, id) || type === "bpmn:SequenceFlow";
}

/** A moddle element, as bpmn-js's getDefinitions() or bpmn-moddle's fromXML() gives it. */
export type ModdleElement = {
  $type: string;
  id?: string;
  name?: string;
  rootElements?: ModdleElement[];
  flowElements?: ModdleElement[];
  sourceRef?: ModdleElement;
  targetRef?: ModdleElement;
};

type Named = { id: string; name: string };

export type BpmnSemantics = {
  tasks: Named[];
  gateways: Named[];
  dataObjects: Named[];
  startEvents: string[];
  /** "source>target" for each sequence flow, sorted. */
  flows: string[];
};
// `tasks` are the steps' tasks only: a generated task is not a step, so it is
// neither compared nor checked for a name or a connection.

const byId = (a: Named, b: Named) => a.id.localeCompare(b.id);

/** What the blueprint sync reads from a model; see the module comment. */
export function bpmnSemantics(definitions: ModdleElement | null | undefined): BpmnSemantics {
  const empty: BpmnSemantics = { tasks: [], gateways: [], dataObjects: [], startEvents: [], flows: [] };
  const process = (definitions?.rootElements ?? []).find((el) => el.$type === "bpmn:Process");
  if (!process) return empty;
  const named = (el: ModdleElement): Named => ({
    id: el.id ?? "",
    name: (el.name ?? "").replace(/\s+/g, " ").trim(),
  });
  const out = empty;
  for (const el of process.flowElements ?? []) {
    if (BPMN_TASK_TYPES.has(el.$type)) {
      if (!isSyntheticBpmnTask(el.id)) out.tasks.push(named(el));
    }
    else if (GATEWAY_TYPES.has(el.$type)) out.gateways.push(named(el));
    else if (el.$type === "bpmn:DataObjectReference") out.dataObjects.push(named(el));
    else if (el.$type === "bpmn:StartEvent" && el.id) out.startEvents.push(el.id);
    else if (el.$type === "bpmn:SequenceFlow" && el.sourceRef?.id && el.targetRef?.id) {
      if (FLOW_NODE_TYPES.has(el.sourceRef.$type) && FLOW_NODE_TYPES.has(el.targetRef.$type)) {
        out.flows.push(`${el.sourceRef.id}>${el.targetRef.id}`);
      }
    }
  }
  out.tasks.sort(byId);
  out.gateways.sort(byId);
  out.dataObjects.sort(byId);
  out.startEvents.sort();
  out.flows.sort();
  return out;
}

const ids = (list: Named[]) => list.map((n) => n.id).join("\n");
const names = (list: Named[]) => list.map((n) => n.name).join("\n");

/**
 * How `current` differs from `base`: not at all, only in names (saved by
 * itself, see BpmnDiagramPanel), or in what is connected to what (saved when
 * the user says so).
 */
export function bpmnChangeKind(base: BpmnSemantics, current: BpmnSemantics): "none" | "rename" | "structure" {
  const sameShape =
    ids(base.tasks) === ids(current.tasks) &&
    ids(base.gateways) === ids(current.gateways) &&
    ids(base.dataObjects) === ids(current.dataObjects) &&
    base.startEvents.join("\n") === current.startEvents.join("\n") &&
    base.flows.join("\n") === current.flows.join("\n");
  if (!sameShape) return "structure";
  const sameNames =
    names(base.tasks) === names(current.tasks) &&
    names(base.gateways) === names(current.gateways) &&
    names(base.dataObjects) === names(current.dataObjects);
  return sameNames ? "none" : "rename";
}

/**
 * What a save would lose: tasks no sequence flow from a start event reaches
 * (the sync drops them, and every step after a removed flow with them), and
 * tasks without a name (the sync would name them by their id). A diagram
 * without a start event is synced in document order, so nothing is unreachable.
 */
export function bpmnSaveProblems(sem: BpmnSemantics): { unconnected: Named[]; unnamed: Named[] } {
  const unnamed = sem.tasks.filter((t) => !t.name);
  if (sem.startEvents.length === 0) return { unconnected: [], unnamed };
  const next = new Map<string, string[]>();
  for (const flow of sem.flows) {
    const [from, to] = flow.split(">");
    next.set(from, [...(next.get(from) ?? []), to]);
  }
  const seen = new Set<string>();
  const queue = [...sem.startEvents];
  while (queue.length) {
    const id = queue.shift()!;
    if (seen.has(id)) continue;
    seen.add(id);
    queue.push(...(next.get(id) ?? []));
  }
  return { unconnected: sem.tasks.filter((t) => !seen.has(t.id)), unnamed };
}

const TASK_TAG = "(?:task|userTask|serviceTask|manualTask|sendTask|callActivity|scriptTask)";

/**
 * Task names without the generator's component codes ("[CLS] Classification"
 * shows as "Classification"). A code is one to four capitals or digits
 * (bpmn_generator._component_code); a name that starts with other brackets
 * ("[Beta] Upload") is the user's and stays whole. The sync strips the same
 * prefix when it reads a name back (bpmn_sync._task_label), and the generator
 * adds it again, so leaving it out of the canvas loses nothing and doubles
 * nothing.
 */
export function stripTaskCodePrefixes(xml: string): string {
  const re = new RegExp(`(<(?:[\\w-]+:)?${TASK_TAG}\\b[^>]*?\\sname=")\\[[A-Z0-9]{1,4}\\]\\s*`, "g");
  return xml.replace(re, "$1");
}

/** The element the generator draws for a step: "classify" → "Activity_classify" (bpmn_generator._safe). */
export function stepIdToBpmnId(stepId: string): string {
  return `Activity_${stepId.replace(/[^\p{L}\p{N}_]/gu, "_")}`;
}

/** The step an element of the diagram stands for, if it stands for one. */
export function stepIndexForBpmnId(steps: { id: string }[], bpmnId: string | null | undefined): number {
  if (!bpmnId) return -1;
  return steps.findIndex((s) => stepIdToBpmnId(s.id) === bpmnId);
}
