// Hand-off of a Source Normalizer result to the Knowledge Curator page within one
// browser tab. sessionStorage is per tab and survives a reload, and a result of a few
// hundred KB fits; when it does not, the caller falls back to the .zip download.
import { parseArtifacts } from "./workspace";

const KEY = "gaik:normalized-handoff";

/** Store the `normalized/` files for the curator page; false if the browser refuses. */
export function putHandoff(artifacts: Record<string, string>): boolean {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(artifacts));
    return true;
  } catch {
    return false; // storage full or unavailable
  }
}

/** The stored files, removed on read so a reload does not reload stale data; null if none. */
export function takeHandoff(): Record<string, string> | null {
  let raw: string | null;
  try {
    raw = sessionStorage.getItem(KEY);
    sessionStorage.removeItem(KEY);
  } catch {
    return null;
  }
  if (raw === null) return null;
  try {
    return parseArtifacts(JSON.parse(raw));
  } catch {
    return null; // corrupt or from another version: ignore
  }
}
