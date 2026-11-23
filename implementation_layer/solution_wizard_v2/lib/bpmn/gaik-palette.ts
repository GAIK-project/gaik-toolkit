/**
 * GAIK workflow palette (spec §15.1) — same semantics as solution_wizard visualizer.py
 * and Mermaid diagrams in the docs website.
 *
 *   input      blue   — user provides data
 *   processing purple — automated / GAIK component step
 *   human      yellow — human-in-the-loop or gateway
 *   output     green  — final / success outcome
 */
export type GaikSemanticRole = "input" | "processing" | "human" | "output" | "reject";

export type GaikShapeColors = {
  fill: string;
  stroke: string;
  icon: string;
};

/** Canonical v1 fills + doc stroke colours (Mermaid style lines). */
export const GAIK_BPMN_COLORS: Record<GaikSemanticRole, GaikShapeColors> = {
  input: { fill: "#dbeafe", stroke: "#3b82f6", icon: "#1d4ed8" },
  processing: { fill: "#f5f3ff", stroke: "#7c3aed", icon: "#6d28d9" },
  human: { fill: "#fefce8", stroke: "#ca8a04", icon: "#a16207" },
  output: { fill: "#dcfce7", stroke: "#16a34a", icon: "#15803d" },
  reject: { fill: "#fee2e2", stroke: "#dc2626", icon: "#b91c1c" },
};

function isHumanReviewName(name: string): boolean {
  const key = name.toLowerCase();
  return (
    key.includes("review") ||
    key.includes("approve") ||
    key.includes("human") ||
    key.includes("manager")
  );
}

export function resolveTaskRole(
  bpmnType?: string,
  name?: string,
  elementId?: string,
): GaikSemanticRole {
  const key = `${name ?? ""} ${elementId ?? ""}`.toLowerCase();

  if (bpmnType === "bpmn:ServiceTask" || bpmnType === "bpmn:SendTask") {
    if (key.includes("submit") || (key.includes("send") && key.includes("database"))) {
      return "output";
    }
    return "processing";
  }

  if (bpmnType === "bpmn:UserTask") {
    return isHumanReviewName(name ?? "") ? "human" : "input";
  }

  return "processing";
}

export function resolveEventRole(
  bpmnType?: string,
  name?: string,
  elementId?: string,
): GaikSemanticRole {
  const key = `${name ?? ""} ${elementId ?? ""}`.toLowerCase();

  if (bpmnType === "bpmn:EndEvent") {
    if (key.includes("reject") || key.includes("fail")) return "reject";
    return "output";
  }

  return "input";
}

export function resolveShapeRole(
  bpmnType?: string,
  name?: string,
  elementId?: string,
): GaikSemanticRole {
  if (
    bpmnType === "bpmn:ExclusiveGateway" ||
    bpmnType === "bpmn:ParallelGateway"
  ) {
    return "human";
  }

  if (bpmnType === "bpmn:StartEvent" || bpmnType === "bpmn:EndEvent") {
    return resolveEventRole(bpmnType, name, elementId);
  }

  if (
    bpmnType === "bpmn:UserTask" ||
    bpmnType === "bpmn:ServiceTask" ||
    bpmnType === "bpmn:SendTask"
  ) {
    return resolveTaskRole(bpmnType, name, elementId);
  }

  if (bpmnType === "bpmn:DataStoreReference") {
    return "output";
  }

  return "input";
}

export function shapeColorsFor(
  bpmnType?: string,
  name?: string,
  elementId?: string,
): GaikShapeColors {
  return GAIK_BPMN_COLORS[resolveShapeRole(bpmnType, name, elementId)];
}
