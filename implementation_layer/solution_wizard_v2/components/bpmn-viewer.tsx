"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import type NavigatedViewer from "bpmn-js/lib/NavigatedViewer";
import {
  applyBpmnStartView,
  fitBpmnView,
  reapplyBpmnView,
  zoomBpmnAroundCenter,
  type BpmnViewMode,
} from "@/lib/bpmn-view-fit";
import { BPMN_VIEWER_OPTIONS } from "@/lib/bpmn-viewer-options";
import "bpmn-js/dist/assets/diagram-js.css";
import "bpmn-js/dist/assets/bpmn-js.css";

/**
 * A read-only diagram. Not on any page at the moment; kept for a read-only
 * view of the workflow (the Workflow tab edits with BpmnModeler).
 */
export type BpmnViewerHandle = {
  zoomIn: () => void;
  zoomOut: () => void;
  fit: () => void;
};

export type BpmnRendererMode = "standard" | "gaik";

export const BpmnViewer = forwardRef<
  BpmnViewerHandle,
  {
    xml: string;
    ariaLabel: string;
    loadErrorLabel: string;
    className?: string;
    /** standard = native bpmn-js shapes (official BPMN 2.0); gaik = custom GAIK renderer */
    rendererMode?: BpmnRendererMode;
  }
>(function BpmnViewer(
  { xml, ariaLabel, loadErrorLabel, className = "", rendererMode = "standard" },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<NavigatedViewer | null>(null);
  const viewModeRef = useRef<BpmnViewMode>("start");
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  const zoomBy = useCallback((factor: number) => {
    const viewer = viewerRef.current;
    const container = containerRef.current;
    if (!viewer || !container) return;
    viewModeRef.current = "manual";
    try {
      zoomBpmnAroundCenter(viewer, factor, container);
    } catch {
      /* viewer tearing down */
    }
  }, []);

  useImperativeHandle(
    ref,
    () => ({
      zoomIn: () => zoomBy(1.25),
      zoomOut: () => zoomBy(1 / 1.25),
      fit: () => {
        const viewer = viewerRef.current;
        if (!viewer) return;
        viewModeRef.current = "fit";
        fitBpmnView(viewer);
      },
    }),
    [zoomBy],
  );

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let cancelled = false;
    setReady(false);
    setError(null);
    viewModeRef.current = "start";

    (async () => {
      viewerRef.current?.destroy();
      viewerRef.current = null;

      const { default: Viewer } = await import("bpmn-js/lib/NavigatedViewer");
      if (cancelled) return;

      type ViewerModule = NonNullable<
        ConstructorParameters<typeof Viewer>[0]
      >["additionalModules"] extends (infer M)[] | undefined
        ? M
        : never;

      const additionalModules: ViewerModule[] = [];
      let viewerOptions: Record<string, unknown> = {};

      if (rendererMode === "gaik") {
        const [customRendererModule, diagramEnrichmentModule] = await Promise.all([
          import("@/lib/bpmn/custom-renderer.module"),
          import("@/lib/bpmn/diagram-enrichment.module"),
        ]);
        if (cancelled) return;
        additionalModules.push(
          customRendererModule.default as ViewerModule,
          diagramEnrichmentModule.default as ViewerModule,
        );
        viewerOptions = { ...BPMN_VIEWER_OPTIONS };
      }

      const viewer = new Viewer({ container, additionalModules, ...viewerOptions });
      viewerRef.current = viewer;

      try {
        await viewer.importXML(xml);
        if (cancelled) return;
        applyBpmnStartView(viewer);
        setReady(true);
      } catch (err) {
        console.error("[BpmnViewer] import failed:", err);
        if (!cancelled) setError(loadErrorLabel);
      }
    })();

    return () => {
      cancelled = true;
      setReady(false);
      viewerRef.current?.destroy();
      viewerRef.current = null;
    };
  }, [xml, loadErrorLabel, rendererMode]);

  useEffect(() => {
    if (!ready) return;
    const container = containerRef.current;
    if (!container) return;
    const ro = new ResizeObserver(() => {
      const viewer = viewerRef.current;
      if (viewer) reapplyBpmnView(viewer, viewModeRef.current);
    });
    ro.observe(container);
    return () => ro.disconnect();
  }, [ready]);

  if (error) {
    return (
      <p className="text-sm text-danger-text" role="alert">
        {error}
      </p>
    );
  }

  return (
    <div
      ref={containerRef}
      className={`bpmn-viewer-themed h-full min-h-[280px] overflow-hidden [&_.bjs-powered-by]:hidden ${className}`}
      role="img"
      aria-label={ariaLabel}
      aria-busy={!ready}
    />
  );
});
