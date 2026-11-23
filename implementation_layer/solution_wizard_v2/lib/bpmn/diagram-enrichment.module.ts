import { is } from "bpmn-js/lib/util/ModelUtil";
import { isLabel } from "bpmn-js/lib/util/LabelUtil";
import { captionHtml, laneHeaderCaptionHtml, stepAboveCaptionHtml } from "./caption-html";
import { formatFullLabel, stepCaptionLines } from "./semantic-icon";

type CanvasLike = {
  addMarker: (elementId: string, marker: string) => void;
};

type RegistryLike = {
  forEach: (fn: (element: BpmnElement) => void) => void;
};

type OverlaysLike = {
  add: (
    elementId: string,
    overlayId: string,
    options: { position: Record<string, number>; html: string },
  ) => void;
};

type BpmnElement = {
  id: string;
  type?: string;
  width?: number;
  height?: number;
  businessObject?: { name?: string };
};

/** Task boxes — full label above the shape; icon only inside the box. */
const TASK_LABEL_TYPES = new Set([
  "bpmn:UserTask",
  "bpmn:ServiceTask",
  "bpmn:SendTask",
  "bpmn:ManualTask",
]);

/** Small shapes — label above, same style as task captions. */
const SMALL_SHAPE_ABOVE_TYPES = new Set([
  "bpmn:StartEvent",
  "bpmn:EndEvent",
  "bpmn:ExclusiveGateway",
  "bpmn:ParallelGateway",
  "bpmn:DataStoreReference",
]);

/** Remaining annotated shapes — label below. */
const STEP_BELOW_TYPES = new Set<string>();

const TASK_CAPTION_LINE_H = 21;
const TASK_CAPTION_PAD = 8;
const TASK_CAPTION_GAP = 12;

function stepCaptionWidth(element: BpmnElement): number {
  const w = element.width ?? 100;
  return Math.max(w, 120);
}

/** Lane title — centered on the lane band top edge. */
const LANE_CAPTION_TOP = 12;
const LANE_CAPTION_SIDE_PAD = 16;

function laneCaptionWidth(element: BpmnElement): number {
  const w = element.width ?? 400;
  return Math.max(160, w - LANE_CAPTION_SIDE_PAD * 2);
}

function laneCaptionPosition(element: BpmnElement): Record<string, number> {
  const laneW = element.width ?? 400;
  const width = laneCaptionWidth(element);
  return {
    top: LANE_CAPTION_TOP,
    left: Math.max(LANE_CAPTION_SIDE_PAD, (laneW - width) / 2),
    width,
  };
}

function taskCaptionHeight(name: string, bpmnType?: string): number {
  const lineCount = Math.max(1, stepCaptionLines(name, bpmnType).length);
  return lineCount * TASK_CAPTION_LINE_H + TASK_CAPTION_PAD * 2;
}

function taskAboveCaptionWidth(element: BpmnElement): number {
  const w = element.width ?? 130;
  return Math.max(w + 40, 180);
}

function smallShapeAboveCaptionWidth(element: BpmnElement): number {
  const w = element.width ?? 36;
  return Math.max(w + 48, 120);
}

function shapeAboveCaptionPosition(
  element: BpmnElement,
  name: string,
  width: number,
): Record<string, number> {
  const w = element.width ?? 36;
  const height = taskCaptionHeight(name, element.type);
  return {
    top: -(height + TASK_CAPTION_GAP),
    left: (w - width) / 2,
    width,
  };
}

function stepCaptionPosition(element: BpmnElement): Record<string, number> {
  const w = element.width ?? 100;
  const h = element.height ?? 80;
  const width = stepCaptionWidth(element);
  const left = (w - width) / 2;
  return { top: h + 10, left, width };
}

function enrichDiagram(
  elementRegistry: RegistryLike,
  canvas: CanvasLike,
  overlays: OverlaysLike,
) {
  elementRegistry.forEach((element) => {
    if (isLabel(element)) {
      canvas.addMarker(element.id, "djs-element-hidden");
    }

    if (is(element, "bpmn:TextAnnotation")) {
      canvas.addMarker(element.id, "djs-element-hidden");
    }
  });

  elementRegistry.forEach((element) => {
    if (!element.type) return;

    if (is(element, "bpmn:Lane")) {
      const raw = element.businessObject?.name ?? "";
      if (!raw.trim()) return;
      const width = laneCaptionWidth(element);
      overlays.add(element.id, "gaik-lane-badge", {
        position: laneCaptionPosition(element),
        html: laneHeaderCaptionHtml(raw, width),
      });
      return;
    }

    const raw = element.businessObject?.name ?? "";
    if (!raw.trim()) return;

    if (TASK_LABEL_TYPES.has(element.type)) {
      const width = taskAboveCaptionWidth(element);
      overlays.add(element.id, "gaik-step-caption", {
        position: shapeAboveCaptionPosition(element, raw, width),
        html: stepAboveCaptionHtml(raw, width, element.type),
      });
      return;
    }

    if (SMALL_SHAPE_ABOVE_TYPES.has(element.type)) {
      const width = smallShapeAboveCaptionWidth(element);
      overlays.add(element.id, "gaik-step-caption", {
        position: shapeAboveCaptionPosition(element, raw, width),
        html: stepAboveCaptionHtml(raw, width, element.type),
      });
      return;
    }

    if (!STEP_BELOW_TYPES.has(element.type)) return;

    const full = formatFullLabel(raw);
    const width = stepCaptionWidth(element);

    overlays.add(element.id, "gaik-step-caption", {
      position: stepCaptionPosition(element),
      html: captionHtml({ short: full, full, width }),
    });
  });
}

class DiagramEnrichment {
  static $inject = ["eventBus", "elementRegistry", "canvas", "overlays"];

  constructor(
    eventBus: { on: (event: string, fn: () => void) => void },
    elementRegistry: RegistryLike,
    canvas: CanvasLike,
    overlays: OverlaysLike,
  ) {
    eventBus.on("import.done", () => {
      try {
        enrichDiagram(elementRegistry, canvas, overlays);
      } catch (err) {
        console.error("[BpmnViewer] diagram enrichment failed:", err);
      }
    });
  }
}

export default {
  __init__: ["diagramEnrichment"],
  diagramEnrichment: ["type", DiagramEnrichment],
};
