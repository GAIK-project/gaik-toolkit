import { describe, expect, it, vi } from "vitest";
import {
  deleteBpmnDraft,
  getBpmnDraft,
  hasBpmnDraft,
  setBpmnDraft,
  subscribeBpmnDrafts,
} from "@/lib/bpmn-session-drafts";

describe("bpmn-session-drafts", () => {
  it("tracks unsaved BPMN drafts per session and notifies subscribers", () => {
    const onChange = vi.fn();
    const unsub = subscribeBpmnDrafts(onChange);
    try {
      expect(hasBpmnDraft("s1")).toBe(false);
      setBpmnDraft("s1", { base: "<base/>", xml: "<edit/>" });
      expect(hasBpmnDraft("s1")).toBe(true);
      expect(getBpmnDraft("s1")).toEqual({ base: "<base/>", xml: "<edit/>" });
      expect(onChange).toHaveBeenCalledTimes(1);

      // Identical write does not fire again.
      setBpmnDraft("s1", { base: "<base/>", xml: "<edit/>" });
      expect(onChange).toHaveBeenCalledTimes(1);

      deleteBpmnDraft("s1");
      expect(hasBpmnDraft("s1")).toBe(false);
      expect(onChange).toHaveBeenCalledTimes(2);
    } finally {
      unsub();
      deleteBpmnDraft("s1");
    }
  });
});
