/** Whether a value holds a JSON object or array, a constructor's options say. */
function isJsonStructure(value: string): boolean {
  // Text may start with a bracket too ("[draft] ..."), so the value is parsed.
  if (!value.startsWith("{") && !value.startsWith("[")) return false;
  try {
    const parsed: unknown = JSON.parse(value);
    return typeof parsed === "object" && parsed !== null;
  } catch {
    return false;
  }
}

/**
 * A step's settings as the Plan tab shows them: the readable ones, and how
 * many it leaves out. A value holding a JSON object or array (a constructor's
 * options, say `transcriber_ctor`) is configuration for the Blueprint tab, not
 * something an approver reads; it is counted, so the plan can say that
 * something is hidden. An empty value says nothing and is neither shown nor
 * counted, and nor is "null", which is how the backend stores a setting
 * without a value.
 */
export function planSettings(settings: Record<string, string> | undefined): {
  readable: [string, string][];
  hidden: number;
} {
  const readable: [string, string][] = [];
  let hidden = 0;
  for (const [key, value] of Object.entries(settings ?? {})) {
    const v = value.trim();
    if (v === "" || v === "null") continue;
    if (isJsonStructure(v)) hidden += 1;
    else readable.push([key, value]);
  }
  return { readable, hidden };
}
