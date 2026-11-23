import { BPMN_VISUAL_STEP, POC_STEP } from "@/lib/mock-sessions";

/** Blueprint ("json"), Työnkulku ("flow") and PoC ("poc"). */
export type WorkspaceTab = "json" | "flow" | "poc";

/**
 * The tabs in the wizard's order. Työnkulku is there only once the BPMN view
 * exists: before it the tab showed the same steps as Blueprint, as a list.
 */
export function visibleTabs(flowShown: boolean): WorkspaceTab[] {
  return flowShown ? ["json", "flow", "poc"] : ["json", "poc"];
}

/**
 * The tab that belongs to the session's phase: the test run from the PoC step
 * on, the diagram in the BPMN phases (8-9), the blueprint before. A session
 * opened at Gate 3 used to land on Työnkulku, not on the test the user came
 * back for. Also the tab the "now" dot marks while another tab is open.
 */
export function tabForStep(step: number, flowShown: boolean): WorkspaceTab {
  if (step >= POC_STEP) return "poc";
  if (step >= BPMN_VISUAL_STEP && flowShown) return "flow";
  return "json";
}

/** A `?tab=` value from the URL, or undefined for none or an unknown one. */
export function parseTabParam(value: string | null | undefined): WorkspaceTab | undefined {
  switch (value?.toLowerCase()) {
    case "poc":
      return "poc";
    case "flow":
    case "workflow":
      return "flow";
    case "json":
    case "blueprint":
      return "json";
    default:
      return undefined;
  }
}

/**
 * Which workspace tab should the panel switch to, if any, when the session's
 * step moves forward — chat progresses the session on its own (router.refresh()
 * after each turn), so a milestone can be reached without the user ever
 * touching this panel (#138, raised by a customer reviewer on 28 Aug: "the
 * chat and this user interface are not in sync"). A finished PoC went
 * completely unseen because the tab sat wherever it was last clicked.
 *
 * Returns null when nothing should change: the step didn't move forward, or
 * it moved forward but didn't cross a milestone. Never suggests moving
 * backward — regressing a step (e.g. Gate rejection) shouldn't yank the tab
 * out from under whatever the user is looking at. The one step back that does
 * move the tab is `tabWhenPocLocks`.
 */
export function nextTabForStepChange(prevStep: number, newStep: number): WorkspaceTab | null {
  if (newStep <= prevStep) return null;
  if (newStep >= POC_STEP && prevStep < POC_STEP) return "poc";
  if (newStep >= BPMN_VISUAL_STEP && prevStep < BPMN_VISUAL_STEP) return "flow";
  return null;
}

/**
 * The tab to switch to when the PoC tab has just been locked, if any. A step
 * back leaves the tab alone, with this one exception: Gate 2 was reopened
 * while the PoC tab was open. The API refuses the package until Gate 2 is
 * approved again, so that tab is now a locked card, and what the reopened
 * gate asks the user to check (the solution's structure) is on the tab of the
 * gate's own phase. A tab whose content is still there (Blueprint, Workflow,
 * the PoC at a reopened Gate 3) stays: nothing was taken from under the user.
 */
export function tabWhenPocLocks(current: WorkspaceTab, step: number, flowShown: boolean): WorkspaceTab | null {
  if (current !== "poc") return null;
  const next = tabForStep(step, flowShown);
  return next === "poc" ? null : next;
}
