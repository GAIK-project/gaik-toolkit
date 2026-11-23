export type SemanticIconKind =
  | "audio"
  | "photo"
  | "transcript"
  | "json"
  | "validation"
  | "approved"
  | "database"
  | "ai"
  | "human"
  | "submit"
  | "record"
  | "start"
  | "end"
  | "reject"
  | "gateway"
  | "enhance"
  | "generic";

const COMPONENT_ICON: Record<string, SemanticIconKind> = {
  transcriber: "audio",
  transcriptenhancer: "enhance",
  extractor: "json",
  llmjudge: "validation",
};

export function resolveSemanticIcon(
  name: string,
  elementId: string,
  bpmnType?: string,
): SemanticIconKind {
  const bracket = name.match(/\[([^\]]+)\]/);
  if (bracket) {
    const key = bracket[1].replace(/\s+/g, "").toLowerCase();
    if (COMPONENT_ICON[key]) return COMPONENT_ICON[key];
  }

  const key = `${name} ${elementId}`.toLowerCase();

  if (bpmnType === "bpmn:StartEvent" || key.includes("start")) return "start";
  if (
    bpmnType === "bpmn:EndEvent" &&
    (key.includes("reject") || key.includes("fail"))
  )
    return "reject";
  if (bpmnType === "bpmn:EndEvent" || key.includes("complete")) return "end";
  if (bpmnType === "bpmn:ExclusiveGateway" || bpmnType === "bpmn:ParallelGateway")
    return "gateway";
  if (key.includes("approved") || key.includes("approve?")) return "gateway";

  if (key.includes("photo") || key.includes("image")) return "photo";
  if (key.includes("audio") || key.includes("voice") || key.includes("transcrib"))
    return "audio";
  if (key.includes("enhance")) return "enhance";
  if (key.includes("transcript")) return "transcript";
  if (key.includes("json") || key.includes("extract")) return "json";
  if (key.includes("valid") || key.includes("judge")) return "validation";
  if (key.includes("approved")) return "approved";
  if (key.includes("database") || key.includes("datastore") || key.includes("store"))
    return "database";
  if (key.includes("submit") || key.includes("send")) return "submit";
  if (key.includes("human") || key.includes("review") || key.includes("manager"))
    return "human";
  if (key.includes("record") || key.includes("observation")) return "record";

  if (bpmnType === "bpmn:UserTask") return "human";
  if (bpmnType === "bpmn:ServiceTask") return "ai";

  return "generic";
}

export function semanticIconPaths(kind: SemanticIconKind): string[] {
  switch (kind) {
    case "start":
      return ["M10 8.5v7l6-3.5-6-3.5Z", "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z"];
    case "end":
      return ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z", "M8.5 12 11 14.5 16 10"];
    case "reject":
      return ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z", "M9 9l6 6", "M15 9l-6 6"];
    case "gateway":
      return ["M12 4v16", "M4 12h16", "M12 3l4 4-4 4-4-4 4-4Z"];
    case "enhance":
      return [
        "M12 3 13.5 8.5 19 9l-4 3.5 1.5 5.5-5-3-5 3 1.5-5.5L5 9l5.5-.5L12 3Z",
        "M18 4 19 6",
      ];
    case "audio":
      return [
        "M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Z",
        "M19 11a7 7 0 0 1-14 0",
        "M12 18v3",
      ];
    case "photo":
      return [
        "M4 7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7Z",
        "M8 11a2 2 0 1 0 0 .1",
        "M4 16l4-4 3 3 2-2 5 5",
      ];
    case "transcript":
      return ["M7 8h10", "M7 12h10", "M7 16h6"];
    case "json":
      return [
        "M8 7a2 2 0 0 0-2 2v1a2 2 0 0 1 0 4v1a2 2 0 0 0 2 2",
        "M16 7a2 2 0 0 1 2 2v1a2 2 0 0 0 0 4v1a2 2 0 0 1-2 2",
      ];
    case "validation":
      return [
        "M12 3 19 6v6c0 4-3 7-7 9-4-2-7-5-7-9V6l7-3Z",
        "M9.5 12 11 13.5 15 10",
      ];
    case "approved":
      return ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z", "M8.5 12 11 14.5 16 10"];
    case "database":
      return [
        "M12 4c4.5 0 8 1.5 8 3.5S16.5 11 12 11 4 9.5 4 7.5 7.5 4 12 4Z",
        "M4 7.5v4c0 2 3.5 3.5 8 3.5s8-1.5 8-3.5v-4",
        "M4 11.5v4c0 2 3.5 3.5 8 3.5s8-1.5 8-3.5v-4",
      ];
    case "human":
      return [
        "M12 12a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z",
        "M5 20a7 7 0 0 1 14 0",
      ];
    case "submit":
      return ["M12 16V6", "M8 10l4-4 4 4", "M5 18h14"];
    case "record":
      return ["M12 14a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z", "M5 12a7 7 0 0 1 14 0"];
    case "ai":
      return [
        "M12 3 14.5 8.5 20 9l-4 3.5L17 19l-5-3-5 3 1-6.5L4 9l5.5-.5L12 3Z",
      ];
    default:
      return [
        "M8 6h8",
        "M8 10h8",
        "M8 14h5",
        "M7 4h10a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z",
      ];
  }
}

export function iconAccentColor(kind: SemanticIconKind): string {
  switch (kind) {
    case "start":
      return "#5fd38a";
    case "end":
    case "approved":
      return "#5fd38a";
    case "reject":
      return "#f08a8a";
    case "gateway":
      return "#d6b878";
    case "audio":
    case "record":
      return "#5bb0d0";
    case "photo":
    case "human":
      return "#e09a52";
    case "transcript":
    case "json":
    case "enhance":
      return "#6fd6c6";
    case "validation":
      return "#5fd38a";
    case "database":
    case "submit":
    case "ai":
      return "#d6b878";
    default:
      return "#8aa3a7";
  }
}

export function taskStrokeColor(bpmnType?: string): string {
  if (bpmnType === "bpmn:UserTask") return "#e09a52";
  if (bpmnType === "bpmn:ServiceTask") return "#d6b878";
  if (bpmnType === "bpmn:SendTask") return "#d6b878";
  return "#6fd6c6";
}

export function formatFullLabel(name: string): string {
  return name
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .join(" · ");
}

export function inBoxLabelLines(name: string): string[] {
  return name
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

/** Caption lines above shapes — preserves BPMN newlines or infers a [role] second line. */
export function stepCaptionLines(name: string, bpmnType?: string): string[] {
  const lines = inBoxLabelLines(name);
  if (lines.length > 1) return lines;

  const primary = lines[0] ?? name.trim();
  if (!primary) return lines;

  const suffix = stepCaptionRoleSuffix(bpmnType, primary);
  if (suffix) return [primary, suffix];
  return [primary];
}

function stepCaptionRoleSuffix(bpmnType?: string, name?: string): string | null {
  const key = (name ?? "").toLowerCase();

  if (bpmnType === "bpmn:SendTask") return "[Integration]";
  if (bpmnType === "bpmn:DataStoreReference") return "[Data store]";
  if (bpmnType === "bpmn:manualTask" || bpmnType === "bpmn:ManualTask") return "[User input]";

  if (bpmnType === "bpmn:UserTask") {
    if (
      key.includes("review") ||
      key.includes("approve") ||
      key.includes("manager")
    ) {
      return "[Human review]";
    }
    return "[User input]";
  }

  return null;
}

export function shortenLabel(name: string, maxLen = 18): string {
  const primary = name.split("\n")[0]?.trim() ?? name;
  if (primary.length <= maxLen) return primary;
  return `${primary.slice(0, maxLen - 1)}…`;
}

export function humanizeToken(name: string): string {
  return name.replace(/_/g, " ").replace(/\s+/g, " ").trim();
}

export function captionText(name: string, bpmnType?: string): { short: string; full: string } {
  const full = formatFullLabel(name);
  if (name.includes("_") && name.length < 40 && !name.includes("\n")) {
    return { short: shortenLabel(humanizeToken(name), 18), full: humanizeToken(name) };
  }

  let maxLen = 18;
  if (bpmnType === "bpmn:Participant") maxLen = 36;
  if (bpmnType === "bpmn:Lane") maxLen = 22;
  if (bpmnType === "bpmn:ExclusiveGateway" || bpmnType === "bpmn:ParallelGateway")
    maxLen = 12;
  if (bpmnType === "bpmn:StartEvent" || bpmnType === "bpmn:EndEvent") maxLen = 14;

  return { short: shortenLabel(name, maxLen), full };
}
