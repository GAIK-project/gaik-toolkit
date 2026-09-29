// Hand-off of curated knowledge from the Knowledge Curator page to the Knowledge Synthesis
// page within one browser tab. sessionStorage is per tab and survives a reload, and the
// knowledge of a few sections fits; when it does not, the caller falls back to the .zip.
import { parseKnowledge } from "./workspace";

const KEY = "gaik:knowledge-handoff";

/** Store the `knowledge/` files for the synthesis page; false if the browser refuses. */
export function putKnowledgeHandoff(knowledge: Record<string, string>): boolean {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(knowledge));
    return true;
  } catch {
    return false; // storage full or unavailable
  }
}

/** The stored files, removed on read so a reload does not reload stale data; null if none. */
export function takeKnowledgeHandoff(): Record<string, string> | null {
  let raw: string | null;
  try {
    raw = sessionStorage.getItem(KEY);
    sessionStorage.removeItem(KEY);
  } catch {
    return null;
  }
  if (raw === null) return null;
  try {
    const files = parseKnowledge(JSON.parse(raw));
    return Object.keys(files).length ? files : null;
  } catch {
    return null; // corrupt or from another version: ignore
  }
}
