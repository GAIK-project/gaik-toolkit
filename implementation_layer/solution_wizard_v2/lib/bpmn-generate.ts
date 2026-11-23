import type { Blueprint } from "@/lib/mock-sessions";
import {
  generateBpmnXmlFromBlueprint,
  syncBlueprintFromBpmnXml,
  type BpmnDrawOptions,
} from "@/lib/bpmn-server";
import {
  apiGetSessionBpmn,
  apiSyncSessionBpmn,
  wizardApiEnabled,
} from "@/lib/wizard-api-client";

/** The diagram with its data objects (the default), or a compact one without them. */
export async function fetchBpmnXmlForSession(
  sessionId: string,
  blueprint: Blueprint,
  { dataObjects = true }: BpmnDrawOptions = {},
): Promise<string> {
  if (wizardApiEnabled()) {
    return apiGetSessionBpmn(sessionId, { dataObjects });
  }
  return generateBpmnXmlFromBlueprint(blueprint, sessionId, { dataObjects });
}

export async function syncSessionBpmn(
  sessionId: string,
  blueprint: Blueprint,
  xml: string,
  { dataObjects = true }: BpmnDrawOptions = {},
): Promise<{ blueprint: Blueprint; xml: string; version?: number }> {
  if (wizardApiEnabled()) {
    const detail = await apiSyncSessionBpmn(sessionId, xml);
    const synced: Blueprint = {
      ...detail.blueprint,
      steps: detail.blueprint.steps.map((s) => ({
        ...s,
        type: s.type as Blueprint["steps"][number]["type"],
      })),
    };
    const regenerated = await apiGetSessionBpmn(sessionId, { dataObjects });
    return { blueprint: synced, xml: regenerated, version: detail.active_version };
  }

  const synced = await syncBlueprintFromBpmnXml(blueprint, xml);
  const regenerated = await generateBpmnXmlFromBlueprint(synced, sessionId, { dataObjects });
  return { blueprint: synced, xml: regenerated };
}
