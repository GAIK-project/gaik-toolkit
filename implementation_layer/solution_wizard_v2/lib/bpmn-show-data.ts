/**
 * "Show data" on the BPMN diagram: with it off, the diagram is drawn without
 * data objects, so it is smaller. The choice is kept in this browser; a
 * browser that blocks storage shows the data.
 */

export const BPMN_SHOW_DATA_KEY = "gaik.bpmn.showData";

type ReadStorage = Pick<Storage, "getItem">;
type WriteStorage = Pick<Storage, "setItem">;

function browserStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

/** Whether the diagram shows its data objects; true unless "hide" was chosen. */
export function readBpmnShowData(storage: ReadStorage | null = browserStorage()): boolean {
  try {
    return storage?.getItem(BPMN_SHOW_DATA_KEY) !== "0";
  } catch {
    return true;
  }
}

/** Remembers the choice; without storage it holds for this page only. */
export function saveBpmnShowData(show: boolean, storage: WriteStorage | null = browserStorage()): void {
  try {
    storage?.setItem(BPMN_SHOW_DATA_KEY, show ? "1" : "0");
  } catch {
    // Storage blocked: not remembered past this page.
  }
}

/** The query string for /bpmn and /bpmn/sync: nothing for the default diagram. */
export function bpmnDataObjectsQuery(show: boolean): string {
  return show ? "" : "?data_objects=0";
}

/** The `data_objects` parameter: true without it or with "1", false with "0", null for anything else. */
export function parseDataObjectsParam(value: string | null): boolean | null {
  if (value === null || value === "1") return true;
  if (value === "0") return false;
  return null;
}
