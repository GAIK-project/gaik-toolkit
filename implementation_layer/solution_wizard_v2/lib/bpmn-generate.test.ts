import { beforeEach, describe, expect, it, vi } from "vitest";

const bpmnServerMock = vi.hoisted(() => ({
  generateBpmnXmlFromBlueprint: vi.fn(),
  syncBlueprintFromBpmnXml: vi.fn(),
}));
vi.mock("@/lib/bpmn-server", () => bpmnServerMock);

const apiMock = vi.hoisted(() => ({
  apiGetSessionBpmn: vi.fn(),
  apiSyncSessionBpmn: vi.fn(),
  enabled: false,
}));
vi.mock("@/lib/wizard-api-client", () => ({
  apiGetSessionBpmn: apiMock.apiGetSessionBpmn,
  apiSyncSessionBpmn: apiMock.apiSyncSessionBpmn,
  wizardApiEnabled: () => apiMock.enabled,
}));

import { fetchBpmnXmlForSession, syncSessionBpmn } from "@/lib/bpmn-generate";

const blueprint = { name: "Demo", description: "", goal: "", steps: [] };

beforeEach(() => {
  vi.clearAllMocks();
  apiMock.enabled = false;
});

describe("fetchBpmnXmlForSession", () => {
  it("generates locally when wizard_api is not enabled", async () => {
    bpmnServerMock.generateBpmnXmlFromBlueprint.mockResolvedValue("<bpmn/>");
    const xml = await fetchBpmnXmlForSession("s1", blueprint);
    expect(xml).toBe("<bpmn/>");
    expect(bpmnServerMock.generateBpmnXmlFromBlueprint).toHaveBeenCalledWith(blueprint, "s1");
    expect(apiMock.apiGetSessionBpmn).not.toHaveBeenCalled();
  });

  it("fetches from wizard_api when enabled", async () => {
    apiMock.enabled = true;
    apiMock.apiGetSessionBpmn.mockResolvedValue("<bpmn-from-api/>");
    const xml = await fetchBpmnXmlForSession("s1", blueprint);
    expect(xml).toBe("<bpmn-from-api/>");
    expect(bpmnServerMock.generateBpmnXmlFromBlueprint).not.toHaveBeenCalled();
  });
});

describe("syncSessionBpmn", () => {
  it("syncs locally when wizard_api is not enabled", async () => {
    bpmnServerMock.syncBlueprintFromBpmnXml.mockResolvedValue(blueprint);
    bpmnServerMock.generateBpmnXmlFromBlueprint.mockResolvedValue("<regenerated/>");
    const result = await syncSessionBpmn("s1", blueprint, "<edited/>");
    expect(bpmnServerMock.syncBlueprintFromBpmnXml).toHaveBeenCalledWith(blueprint, "<edited/>");
    expect(result).toEqual({ blueprint, xml: "<regenerated/>" });
  });

  it("syncs via wizard_api when enabled, converting step types, then re-fetches the diagram", async () => {
    apiMock.enabled = true;
    apiMock.apiSyncSessionBpmn.mockResolvedValue({
      blueprint: { ...blueprint, steps: [{ id: "a", name: "A", type: "ai" }] },
    });
    apiMock.apiGetSessionBpmn.mockResolvedValue("<regenerated-from-api/>");
    const result = await syncSessionBpmn("s1", blueprint, "<edited/>");
    expect(apiMock.apiSyncSessionBpmn).toHaveBeenCalledWith("s1", "<edited/>");
    expect(result.xml).toBe("<regenerated-from-api/>");
    expect(result.blueprint.steps[0].type).toBe("ai");
    expect(bpmnServerMock.syncBlueprintFromBpmnXml).not.toHaveBeenCalled();
  });
});
