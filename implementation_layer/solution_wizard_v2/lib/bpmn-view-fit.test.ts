import { describe, expect, it, vi } from "vitest";
import {
  BPMN_MAX_ZOOM,
  BPMN_MIN_ZOOM,
  BPMN_READABLE_MIN_ZOOM,
  applyBpmnStartView,
  centerBpmnElement,
  fitBpmnView,
  reapplyBpmnView,
  zoomBpmnAroundCenter,
} from "./bpmn-view-fit";

type Box = { x: number; y: number; width: number; height: number };

/**
 * A canvas that records what was asked of it. `inner` is the diagram's own
 * box, `outer` the container's size, `scale` the zoom it starts on.
 */
function fakeViewer({
  scale = 0.5,
  inner = { x: 0, y: 0, width: 1000, height: 500 },
  outer = { width: 800, height: 600 },
  start = { type: "bpmn:StartEvent", x: 100, y: 200, width: 36, height: 36 },
}: {
  scale?: number;
  inner?: Box;
  outer?: { width: number; height: number };
  start?: { type: string; x: number; y: number; width: number; height: number } | null;
} = {}) {
  const calls: string[] = [];
  let box: Box = { x: 0, y: 0, width: outer.width / scale, height: outer.height / scale };
  const canvas = {
    resized: vi.fn(() => calls.push("resized")),
    zoom: vi.fn((level?: number | string, center?: unknown) => {
      if (level === undefined) return scale;
      calls.push(`zoom:${String(level)}:${JSON.stringify(center)}`);
      scale = Number(level);
      box = { ...box, width: outer.width / scale, height: outer.height / scale };
      return scale;
    }),
    viewbox: vi.fn((next?: Box) => {
      if (next) {
        calls.push("viewbox");
        box = next;
        scale = outer.width / next.width;
      }
      return { ...box, scale, inner, outer };
    }),
  };
  const registry = {
    filter: (fn: (el: { type?: string }) => boolean) => (start && fn(start) ? [start] : []),
    get: () => undefined,
  };
  const viewer = { get: (name: string) => (name === "canvas" ? canvas : registry) };
  /** Where a point of the diagram is on the screen, in the view set last. */
  const onScreen = (x: number, y: number) => ({ x: (x - box.x) * scale, y: (y - box.y) * scale });
  return { viewer, canvas, calls, onScreen, zoom: () => scale };
}

describe("BPMN view fit and zoom", () => {
  it("fits the whole diagram into the middle of the canvas, measured as it is now", () => {
    const { viewer, calls, onScreen, zoom } = fakeViewer();
    fitBpmnView(viewer);
    // The size is read again first: a grown container is fitted as it is now.
    expect(calls).toEqual(["resized", "viewbox"]);
    // 1000 × 500 into 800 × 600 with 16 px free at each edge: width decides.
    expect(zoom()).toBeCloseTo(0.768);
    expect(onScreen(0, 0).x).toBeCloseTo(16);
    expect(onScreen(1000, 500).x).toBeCloseTo(784);
    expect(onScreen(0, 0).y).toBeCloseTo(108);
    expect(onScreen(1000, 500).y).toBeCloseTo(492);
  });

  it("keeps a fitted diagram clear of the controls at the canvas's edges", () => {
    const { viewer, onScreen } = fakeViewer();
    fitBpmnView(viewer, { left: 64, top: 52, right: 16, bottom: 16 });
    expect(onScreen(0, 0).x).toBeCloseTo(64);
    expect(onScreen(1000, 500).x).toBeCloseTo(784);
    expect(onScreen(0, 0).y).toBeGreaterThanOrEqual(52);
  });

  it("never enlarges a small diagram past 100 %", () => {
    const { viewer, zoom } = fakeViewer({ inner: { x: 0, y: 0, width: 300, height: 200 } });
    fitBpmnView(viewer);
    expect(zoom()).toBe(1);
  });

  it("does not fit into a container without a size (a hidden tab)", () => {
    const { viewer, calls } = fakeViewer({ outer: { width: 0, height: 0 } });
    fitBpmnView(viewer);
    applyBpmnStartView(viewer);
    expect(calls).toEqual(["resized", "resized"]);
  });

  it("opens on the whole diagram when its labels stay readable", () => {
    const { viewer, zoom, onScreen } = fakeViewer();
    applyBpmnStartView(viewer);
    expect(zoom()).toBeCloseTo(0.768);
    expect(onScreen(1000, 500).x).toBeCloseTo(784);
  });

  it("opens on the readable zoom from where the process starts when the fit would be too small", () => {
    // 1000 × 900 into 600 × 400 would fit at 41 %.
    const { viewer, zoom, onScreen } = fakeViewer({
      inner: { x: 0, y: 0, width: 1000, height: 900 },
      outer: { width: 600, height: 400 },
      start: { type: "bpmn:StartEvent", x: 100, y: 582, width: 36, height: 36 },
    });
    applyBpmnStartView(viewer, { left: 64, top: 16, right: 16, bottom: 16 });
    expect(zoom()).toBeCloseTo(BPMN_READABLE_MIN_ZOOM);
    // The diagram's left edge is beside the palette, the start event at mid-height.
    expect(onScreen(0, 0).x).toBeCloseTo(64);
    expect(onScreen(100, 600).y).toBeCloseTo(200);
  });

  it("does not open past the diagram's own top when the start event is near it", () => {
    const { viewer, onScreen } = fakeViewer({
      inner: { x: 0, y: 0, width: 1000, height: 900 },
      outer: { width: 600, height: 400 },
      start: { type: "bpmn:StartEvent", x: 100, y: 40, width: 36, height: 36 },
    });
    applyBpmnStartView(viewer);
    expect(onScreen(0, 0).y).toBeCloseTo(16);
  });

  it("keeps the view the user picked when the container resizes, and re-fits the others", () => {
    const manual = fakeViewer();
    reapplyBpmnView(manual.viewer, "manual");
    expect(manual.calls).toEqual(["resized"]);

    const fit = fakeViewer({ outer: { width: 600, height: 400 } });
    reapplyBpmnView(fit.viewer, "fit");
    expect(fit.zoom()).toBeCloseTo(0.568);

    const start = fakeViewer({ outer: { width: 600, height: 400 } });
    reapplyBpmnView(start.viewer, "start");
    expect(start.zoom()).toBeCloseTo(BPMN_READABLE_MIN_ZOOM);
  });

  it("zooms around the middle of the visible area, not the corner", () => {
    const { viewer, calls } = fakeViewer({ scale: 0.5 });
    const scale = zoomBpmnAroundCenter(viewer, 1.25, { clientWidth: 676, clientHeight: 646 });
    expect(scale).toBeCloseTo(0.625);
    expect(calls).toEqual(["resized", 'zoom:0.625:{"x":338,"y":323}']);
  });

  it("keeps the toolbar's zoom limits", () => {
    expect(
      zoomBpmnAroundCenter(fakeViewer({ scale: 3.9 }).viewer, 1.25, { clientWidth: 10, clientHeight: 10 }),
    ).toBe(BPMN_MAX_ZOOM);
    expect(
      zoomBpmnAroundCenter(fakeViewer({ scale: 0.21 }).viewer, 0.5, { clientWidth: 10, clientHeight: 10 }),
    ).toBe(BPMN_MIN_ZOOM);
  });

  it("centres a step at a readable zoom", () => {
    const { viewer, onScreen, zoom } = fakeViewer({ scale: 0.5, outer: { width: 720, height: 360 } });
    centerBpmnElement(viewer, { x: 400, y: 300, width: 100, height: 80 });
    expect(zoom()).toBeCloseTo(BPMN_READABLE_MIN_ZOOM);
    expect(onScreen(450, 340)).toEqual({ x: 360, y: 180 });
  });

  it("centres a step in what the properties panel leaves free", () => {
    const { viewer, onScreen } = fakeViewer({ scale: 1, outer: { width: 800, height: 400 } });
    centerBpmnElement(viewer, { x: 400, y: 300, width: 100, height: 80 }, { left: 60, top: 56, right: 312, bottom: 16 });
    // Free area: x 60..488, y 56..384.
    expect(onScreen(450, 340)).toEqual({ x: 274, y: 220 });
  });

  it("centres a step at the zoom the user has when that is larger", () => {
    const { viewer, onScreen, zoom } = fakeViewer({ scale: 1.2, outer: { width: 720, height: 360 } });
    centerBpmnElement(viewer, { x: 400, y: 300, width: 100, height: 80 });
    expect(zoom()).toBeCloseTo(1.2);
    expect(onScreen(450, 340).x).toBeCloseTo(360);
  });
});
