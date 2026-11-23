/**
 * How bpmn-js draws shapes and labels, for the modeler and the read-only
 * viewer: the app's own surface, ink and typeface (app/globals.css @theme),
 * so the diagram reads as part of the page.
 */
const FONT_FAMILY = '"Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif';

export const BPMN_VIEWER_OPTIONS = {
  textRenderer: {
    defaultStyle: {
      fontFamily: FONT_FAMILY,
      fontSize: "12px",
      fontWeight: "500",
      lineHeight: 1.3,
    },
    externalStyle: {
      fontFamily: FONT_FAMILY,
      fontSize: "11px",
      fontWeight: "500",
      lineHeight: 1.3,
    },
  },
  bpmnRenderer: {
    defaultFillColor: "#ffffff",
    defaultStrokeColor: "#333d4f",
    defaultLabelColor: "#111b28",
  },
} as const;
