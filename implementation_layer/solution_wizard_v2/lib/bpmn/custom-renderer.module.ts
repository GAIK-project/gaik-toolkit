import BaseRenderer from "diagram-js/lib/draw/BaseRenderer";
import { is } from "bpmn-js/lib/util/ModelUtil";
import {
  append as svgAppend,
  attr as svgAttr,
  create as svgCreate,
} from "tiny-svg";
import {
  formatFullLabel,
  resolveSemanticIcon,
  semanticIconPaths,
} from "./semantic-icon";
import { shapeColorsFor, resolveShapeRole } from "./gaik-palette";

const HIGH_PRIORITY = 1600;
const TASK_RADIUS = 10;

function drawIconGroup(
  parentGfx: SVGElement,
  kind: ReturnType<typeof resolveSemanticIcon>,
  x: number,
  y: number,
  size: number,
  accent: string,
) {
  const group = svgCreate("g");
  svgAttr(group, { transform: `translate(${x}, ${y})` });

  for (const d of semanticIconPaths(kind)) {
    const path = svgCreate("path");
    svgAttr(path, {
      d,
      fill: "none",
      stroke: accent,
      "stroke-width": 1.8,
      "stroke-linecap": "round",
      "stroke-linejoin": "round",
      transform: `scale(${size / 24})`,
      class: "gaik-icon",
    });
    svgAppend(group, path);
  }

  svgAppend(parentGfx, group);
  return group;
}

function attachShapeTooltip(node: SVGElement, name: string) {
  const title = svgCreate("title");
  title.textContent = formatFullLabel(name);
  svgAppend(node, title);
}

function drawTaskShape(
  parentGfx: SVGElement,
  element: { width?: number; height?: number; type?: string; businessObject?: { name?: string }; id?: string },
) {
  const w = element.width ?? 130;
  const h = element.height ?? 90;
  const name = element.businessObject?.name ?? element.id ?? "";
  const kind = resolveSemanticIcon(name, element.id ?? "", element.type);
  const colors = shapeColorsFor(element.type, name, element.id);
  const role = resolveShapeRole(element.type, name, element.id);

  const rect = svgCreate("rect");
  svgAttr(rect, {
    x: 0,
    y: 0,
    width: w,
    height: h,
    rx: TASK_RADIUS,
    ry: TASK_RADIUS,
    fill: colors.fill,
    stroke: colors.stroke,
    "stroke-width": 2,
    class: `gaik-node-shape gaik-task-shape gaik-role-${role}`,
  });
  svgAppend(parentGfx, rect);

  const iconSize = 36;
  drawIconGroup(
    parentGfx,
    kind,
    w / 2 - iconSize / 2,
    h / 2 - iconSize / 2,
    iconSize,
    colors.icon,
  );
  attachShapeTooltip(rect, name);
  return rect;
}

function drawEventShape(
  parentGfx: SVGElement,
  element: { width?: number; height?: number; type?: string; businessObject?: { name?: string }; id?: string },
) {
  const size = element.width ?? 36;
  const name = element.businessObject?.name ?? element.id ?? "";
  const kind = resolveSemanticIcon(name, element.id ?? "", element.type);
  const colors = shapeColorsFor(element.type, name, element.id);
  const role = resolveShapeRole(element.type, name, element.id);
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 2;

  const circle = svgCreate("circle");
  svgAttr(circle, {
    cx,
    cy,
    r,
    fill: colors.fill,
    stroke: colors.stroke,
    "stroke-width": 2.5,
    class: `gaik-node-shape gaik-role-${role}`,
  });
  svgAppend(parentGfx, circle);
  drawIconGroup(parentGfx, kind, cx - 9, cy - 9, 18, colors.icon);
  attachShapeTooltip(circle, name);
  return circle;
}

function drawGatewayShape(
  parentGfx: SVGElement,
  element: { width?: number; height?: number; businessObject?: { name?: string }; id?: string; type?: string },
) {
  const w = element.width ?? 50;
  const h = element.height ?? 50;
  const name = element.businessObject?.name ?? element.id ?? "";
  const kind = resolveSemanticIcon(name, element.id ?? "", element.type);
  const colors = shapeColorsFor(element.type, name, element.id);
  const role = resolveShapeRole(element.type, name, element.id);
  const cx = w / 2;
  const cy = h / 2;
  const d = `M ${cx} 2 L ${w - 2} ${cy} L ${cx} ${h - 2} L 2 ${cy} Z`;

  const diamond = svgCreate("path");
  svgAttr(diamond, {
    d,
    fill: colors.fill,
    stroke: colors.stroke,
    "stroke-width": 2,
    class: `gaik-node-shape gaik-role-${role}`,
  });
  svgAppend(parentGfx, diamond);
  drawIconGroup(parentGfx, kind, cx - 8, cy - 8, 16, colors.icon);
  attachShapeTooltip(diamond, name);
  return diamond;
}

function drawDataObject(
  parentGfx: SVGElement,
  element: { width?: number; height?: number; businessObject?: { name?: string }; id?: string; type?: string },
) {
  const w = element.width ?? 36;
  const h = element.height ?? 50;
  const name = element.businessObject?.name ?? element.id ?? "";
  const kind = resolveSemanticIcon(name, element.id ?? "", element.type);
  const colors = shapeColorsFor(element.type, name, element.id);
  const role = resolveShapeRole(element.type, name, element.id);

  const box = svgCreate("rect");
  svgAttr(box, {
    x: 0,
    y: 0,
    width: w,
    height: h,
    rx: 8,
    ry: 8,
    fill: colors.fill,
    stroke: colors.stroke,
    "stroke-width": 2,
    class: `gaik-node-shape gaik-role-${role}`,
  });
  svgAppend(parentGfx, box);
  drawIconGroup(parentGfx, kind, w / 2 - 11, h / 2 - 11, 22, colors.icon);
  attachShapeTooltip(box, name);
  return box;
}

function drawDataStore(
  parentGfx: SVGElement,
  element: { width?: number; height?: number; businessObject?: { name?: string }; id?: string; type?: string },
) {
  const w = element.width ?? 50;
  const h = element.height ?? 50;
  const name = element.businessObject?.name ?? element.id ?? "";
  const kind = resolveSemanticIcon(name, element.id ?? "", element.type);
  const colors = shapeColorsFor(element.type, name, element.id);
  const role = resolveShapeRole(element.type, name, element.id);

  const body = svgCreate("path");
  svgAttr(body, {
    d: `M2 ${h * 0.22} C2 ${h * 0.08} ${w / 2} ${h * 0.02} ${w / 2} ${h * 0.02} S${w - 2} ${h * 0.08} ${w - 2} ${h * 0.22} V${h - 4} C${w - 2} ${h - 2} ${w / 2} ${h - 1} ${w / 2} ${h - 1} S2 ${h - 2} 2 ${h - 4} Z`,
    fill: colors.fill,
    stroke: colors.stroke,
    "stroke-width": 2,
    class: `gaik-node-shape gaik-role-${role}`,
  });
  svgAppend(parentGfx, body);
  drawIconGroup(parentGfx, kind, w / 2 - 10, h / 2 - 6, 20, colors.icon);
  attachShapeTooltip(body, name);
  return body;
}

class SemanticBpmnRenderer extends BaseRenderer {
  static $inject = ["eventBus", "bpmnRenderer"];

  private bpmnRenderer: {
    drawShape: (parentGfx: SVGElement, element: unknown) => SVGElement;
    getShapePath: (shape: unknown) => string;
  };

  constructor(
    eventBus: unknown,
    bpmnRenderer: SemanticBpmnRenderer["bpmnRenderer"],
  ) {
    super(eventBus as ConstructorParameters<typeof BaseRenderer>[0], HIGH_PRIORITY);
    this.bpmnRenderer = bpmnRenderer;
  }

  canRender(element: unknown) {
    const el = element as { labelTarget?: unknown };
    if (el.labelTarget) return false;
    return (
      is(element, "bpmn:UserTask") ||
      is(element, "bpmn:ServiceTask") ||
      is(element, "bpmn:SendTask") ||
      is(element, "bpmn:StartEvent") ||
      is(element, "bpmn:EndEvent") ||
      is(element, "bpmn:ExclusiveGateway") ||
      is(element, "bpmn:ParallelGateway") ||
      is(element, "bpmn:DataObjectReference") ||
      is(element, "bpmn:DataStoreReference")
    );
  }

  drawShape(parentGfx: SVGElement, element: unknown) {
    const el = element as {
      type?: string;
      id?: string;
      width?: number;
      height?: number;
      businessObject?: { name?: string };
    };

    if (is(element, "bpmn:UserTask") || is(element, "bpmn:ServiceTask") || is(element, "bpmn:SendTask")) {
      return drawTaskShape(parentGfx, el);
    }
    if (is(element, "bpmn:StartEvent") || is(element, "bpmn:EndEvent")) {
      return drawEventShape(parentGfx, el);
    }
    if (is(element, "bpmn:ExclusiveGateway") || is(element, "bpmn:ParallelGateway")) {
      return drawGatewayShape(parentGfx, el);
    }
    if (is(element, "bpmn:DataObjectReference")) {
      return drawDataObject(parentGfx, el);
    }
    if (is(element, "bpmn:DataStoreReference")) {
      return drawDataStore(parentGfx, el);
    }

    return this.bpmnRenderer.drawShape(parentGfx, element);
  }

  getShapePath(shape: unknown) {
    const el = shape as { width?: number; height?: number; type?: string };
    const w = el.width ?? 36;
    const h = el.height ?? 36;

    if (is(shape, "bpmn:UserTask") || is(shape, "bpmn:ServiceTask") || is(shape, "bpmn:SendTask")) {
      return `M0,0 L${w},0 L${w},${h} L0,${h} Z`;
    }
    if (is(shape, "bpmn:StartEvent") || is(shape, "bpmn:EndEvent")) {
      const r = w / 2 - 2;
      const cx = w / 2;
      const cy = h / 2;
      return `M ${cx - r},${cy} A ${r},${r} 0 1,0 ${cx + r},${cy} A ${r},${r} 0 1,0 ${cx - r},${cy}`;
    }
    if (is(shape, "bpmn:ExclusiveGateway") || is(shape, "bpmn:ParallelGateway")) {
      const cx = w / 2;
      const cy = h / 2;
      return `M ${cx} 2 L ${w - 2} ${cy} L ${cx} ${h - 2} L 2 ${cy} Z`;
    }
    if (is(shape, "bpmn:DataObjectReference")) {
      return `M0,0 L${w},0 L${w},${h} L0,${h} Z`;
    }

    return this.bpmnRenderer.getShapePath(shape);
  }
}

export default {
  __init__: ["semanticBpmnRenderer"],
  semanticBpmnRenderer: ["type", SemanticBpmnRenderer],
};
