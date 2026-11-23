import type { Blueprint } from "@/lib/mock-sessions";
import {
  generateBpmnXmlFromBlueprint,
  syncBlueprintFromBpmnXml,
} from "@/lib/bpmn-server";
import {
  apiGetSessionBpmn,
  apiSyncSessionBpmn,
  wizardApiEnabled,
} from "@/lib/wizard-api-client";

export async function fetchBpmnXmlForSession(
  sessionId: string,
  blueprint: Blueprint,
): Promise<string> {
  if (wizardApiEnabled()) {
    return apiGetSessionBpmn(sessionId);
  }
  return generateBpmnXmlFromBlueprint(blueprint, sessionId);
}

export async function syncSessionBpmn(
  sessionId: string,
  blueprint: Blueprint,
  xml: string,
): Promise<{ blueprint: Blueprint; xml: string }> {
  if (wizardApiEnabled()) {
    const detail = await apiSyncSessionBpmn(sessionId, xml);
    const synced: Blueprint = {
      ...detail.blueprint,
      steps: detail.blueprint.steps.map((s) => ({
        ...s,
        type: s.type as Blueprint["steps"][number]["type"],
      })),
    };
    const regenerated = await apiGetSessionBpmn(sessionId);
    return { blueprint: synced, xml: regenerated };
  }

  const synced = await syncBlueprintFromBpmnXml(blueprint, xml);
  const regenerated = await generateBpmnXmlFromBlueprint(synced, sessionId);
  return { blueprint: synced, xml: regenerated };
}
