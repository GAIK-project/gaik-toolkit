/** Minimum zoom where the diagram's labels stay legible on typical laptop viewports. */
export const BPMN_READABLE_MIN_ZOOM = 0.72;

/** Zoom limits of the toolbar's + and − buttons. */
export const BPMN_MIN_ZOOM = 0.2;
export const BPMN_MAX_ZOOM = 4;

/**
 * How the view was chosen, so a resize can keep it:
 * - "start": the view the diagram opens on (see applyBpmnStartView);
 * - "fit": the user asked for the whole diagram ("Sovita näkymään");
 * - "manual": the user zoomed, panned or picked a step, and keeps that view.
 */
export type BpmnViewMode = "start" | "fit" | "manual";

/**
 * Screen pixels at the canvas's edges that controls cover (the palette on the
 * left, the zoom controls at the top), so a fitted diagram is not under them.
 */
export type BpmnViewInset = { left: number; top: number; right: number; bottom: number };

const NO_INSET: BpmnViewInset = { left: 16, top: 16, right: 16, bottom: 16 };

type Box = { x: number; y: number; width: number; height: number };

type CanvasLike = {
  zoom: (level?: number | string, center?: { x: number; y: number } | string) => number;
  viewbox: (box?: Box) => { inner: Box; outer?: { width: number; height: number } } & Box;
  resized?: () => void;
};

type ElementLike = {
  type?: string;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
};

type RegistryLike = {
  filter: (fn: (el: ElementLike) => boolean) => ElementLike[];
  get: (id: string) => ElementLike | undefined;
};

type ViewerLike = {
  get: (name: string) => unknown;
};

/**
 * Tell diagram-js the container may have changed size, and read the size.
 *
 * The canvas caches its viewbox, outer size included, and fits and zooms
 * against that cache. A container that grew after the first fit (the tab
 * opening, the side panel settling) left the diagram fitted to the old size:
 * small, in a corner, partly outside the view, and every zoom then turned
 * around the old centre, pushing it further out.
 *
 * Returns null while the container has no size (a hidden tab): a fit
 * against nothing sets an infinite zoom that the next fit cannot undo.
 */
function sized(canvas: CanvasLike): { inner: Box; outer: { width: number; height: number } } | null {
  canvas.resized?.();
  const { inner, outer } = canvas.viewbox();
  if (!outer || outer.width <= 0 || outer.height <= 0) return null;
  return { inner, outer };
}

/** The zoom at which the whole diagram fits the canvas inside `inset`; never above 100 %. */
function fitZoom(inner: Box, outer: { width: number; height: number }, inset: BpmnViewInset): number {
  if (inner.width <= 0 || inner.height <= 0) return 1;
  const width = Math.max(outer.width - inset.left - inset.right, 1);
  const height = Math.max(outer.height - inset.top - inset.bottom, 1);
  return Math.min(1, width / inner.width, height / inner.height);
}

/** The whole diagram in the view ("Sovita näkymään"), in the middle of what the controls leave free. */
export function fitBpmnView(viewer: ViewerLike, inset: BpmnViewInset = NO_INSET) {
  const canvas = viewer.get("canvas") as CanvasLike;
  const size = sized(canvas);
  if (!size) return;
  const { inner, outer } = size;
  const zoom = fitZoom(inner, outer, inset);
  const freeWidth = outer.width - inset.left - inset.right;
  const freeHeight = outer.height - inset.top - inset.bottom;
  canvas.viewbox({
    x: inner.x - (inset.left + (freeWidth - inner.width * zoom) / 2) / zoom,
    y: inner.y - (inset.top + (freeHeight - inner.height * zoom) / 2) / zoom,
    width: outer.width / zoom,
    height: outer.height / zoom,
  });
}

/**
 * The view a diagram opens on: the whole diagram when its labels stay
 * readable that way; otherwise the readable zoom with the diagram's left edge
 * (where the process starts) at the canvas's left edge and the start event at
 * mid-height, and the rest one drag away.
 */
export function applyBpmnStartView(viewer: ViewerLike, inset: BpmnViewInset = NO_INSET) {
  const canvas = viewer.get("canvas") as CanvasLike;
  const size = sized(canvas);
  if (!size) return;
  const { inner, outer } = size;
  if (fitZoom(inner, outer, inset) >= BPMN_READABLE_MIN_ZOOM) {
    fitBpmnView(viewer, inset);
    return;
  }
  const zoom = BPMN_READABLE_MIN_ZOOM;
  const height = outer.height / zoom;
  const top = inner.y - inset.top / zoom;
  const bottom = inner.y + inner.height + inset.bottom / zoom;
  const registry = viewer.get("elementRegistry") as RegistryLike;
  const start = registry.filter((el) => el.type === "bpmn:StartEvent")[0];
  const focusY =
    start?.y != null && start.height != null ? start.y + start.height / 2 : inner.y + inner.height / 2;
  // The start event at mid-height, but never past the diagram's own top or bottom.
  const y =
    bottom - top <= height
      ? top - (height - (bottom - top)) / 2
      : Math.min(Math.max(focusY - height / 2, top), bottom - height);
  canvas.viewbox({ x: inner.x - inset.left / zoom, y, width: outer.width / zoom, height });
}

/**
 * After the container changed size: the start view and the fit are chosen
 * again for the new size; a view the user picked stays as it is.
 */
export function reapplyBpmnView(viewer: ViewerLike, mode: BpmnViewMode, inset: BpmnViewInset = NO_INSET) {
  if (mode === "start") applyBpmnStartView(viewer, inset);
  else if (mode === "fit") fitBpmnView(viewer, inset);
  else sized(viewer.get("canvas") as CanvasLike);
}

/** Zoom by `factor` around the middle of what the user sees, within the toolbar's limits. */
export function zoomBpmnAroundCenter(
  viewer: ViewerLike,
  factor: number,
  container: { clientWidth: number; clientHeight: number },
): number {
  const canvas = viewer.get("canvas") as CanvasLike;
  canvas.resized?.();
  const next = Math.min(BPMN_MAX_ZOOM, Math.max(BPMN_MIN_ZOOM, canvas.zoom() * factor));
  return canvas.zoom(next, { x: container.clientWidth / 2, y: container.clientHeight / 2 });
}

/**
 * Move the view so `element` is in the middle of what `inset` leaves free
 * (the properties panel opens over the canvas when a step is picked), at the
 * zoom the user has, or at the readable zoom when the view is smaller than that.
 */
export function centerBpmnElement(viewer: ViewerLike, element: ElementLike, inset: BpmnViewInset = NO_INSET) {
  const canvas = viewer.get("canvas") as CanvasLike;
  const size = sized(canvas);
  if (!size) return;
  if (element.x == null || element.y == null) return;
  const { outer } = size;
  const zoom = Math.max(canvas.zoom(), BPMN_READABLE_MIN_ZOOM);
  const cx = element.x + (element.width ?? 0) / 2;
  const cy = element.y + (element.height ?? 0) / 2;
  // Where the element's middle goes on the screen; the canvas's own middle when the inset leaves no room.
  const free = (start: number, end: number, full: number) =>
    full - start - end > 0 ? start + (full - start - end) / 2 : full / 2;
  canvas.viewbox({
    x: cx - free(inset.left, inset.right, outer.width) / zoom,
    y: cy - free(inset.top, inset.bottom, outer.height) / zoom,
    width: outer.width / zoom,
    height: outer.height / zoom,
  });
}
