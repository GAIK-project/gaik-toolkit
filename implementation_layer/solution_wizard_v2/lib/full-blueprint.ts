/**
 * The full blueprint view's logic (components/full-blueprint-view): the
 * draft as `GET /api/sessions/{id}/blueprint/full` answers it, its text in
 * the advanced editor, where the read-only sections stand in that text, and
 * the checks made before a save is sent (the JSON parses, it is an object, no
 * read-only section changed). wizard_api checks the same again.
 */

export type Draft = Record<string, unknown>;

export type FullBlueprint = {
  /** The session's active version the draft was read at: the save's `base_version`. */
  version: number;
  draft: Draft;
  /** The draft file's digest: the save's `base_digest`. */
  draftDigest: string;
  /** The sections only the wizard writes. */
  readonlySections: string[];
};

const isObject = (v: unknown): v is Draft => !!v && typeof v === "object" && !Array.isArray(v);

/** The GET answer `{version, draft, draft_digest, readonly_sections}`, or null for anything else. */
export function readFullBlueprint(body: unknown): FullBlueprint | null {
  if (!isObject(body)) return null;
  const { version, draft, draft_digest, readonly_sections } = body;
  if (typeof version !== "number" || !isObject(draft) || typeof draft_digest !== "string") return null;
  return {
    version,
    draft,
    draftDigest: draft_digest,
    readonlySections: Array.isArray(readonly_sections)
      ? readonly_sections.filter((s): s is string => typeof s === "string")
      : [],
  };
}

/** The draft as the editor and the download show it. */
export function draftText(draft: Draft): string {
  return JSON.stringify(draft, null, 2);
}

/**
 * Where each read-only section's property (`"metadata": {...}`, without the
 * comma after it) stands in `draftText`'s text. A top-level key is the only
 * one written at two spaces after a line break: JSON.stringify escapes the
 * line breaks inside strings.
 */
export function readonlyRanges(text: string, sections: readonly string[]): { from: number; to: number }[] {
  const keys = [...text.matchAll(/\n {2}"((?:[^"\\]|\\.)*)": /g)];
  const close = text.lastIndexOf("\n}");
  const ranges: { from: number; to: number }[] = [];
  keys.forEach((match, i) => {
    let key: string;
    try {
      key = JSON.parse(`"${match[1]}"`) as string;
    } catch {
      return;
    }
    if (!sections.includes(key)) return;
    const from = match.index + 3;
    let to = i + 1 < keys.length ? keys[i + 1].index : close;
    if (text[to - 1] === ",") to -= 1;
    ranges.push({ from, to });
  });
  return ranges;
}

/**
 * Where JSON that does not parse goes wrong, as an offset into `text`; -1
 * when it parses. Browsers word JSON.parse's errors differently, and some
 * without a place, so the text is scanned here.
 */
export function jsonErrorLocation(text: string): number {
  let i = 0;
  const fail = (): never => {
    throw i;
  };
  const ws = () => {
    while (i < text.length && " \t\n\r".includes(text[i])) i++;
  };
  const string = () => {
    i++;
    while (i < text.length) {
      const c = text[i];
      if (c === '"') {
        i++;
        return;
      }
      if (c === "\\") {
        i++;
        if (text[i] === "u") {
          if (!/^[0-9a-fA-F]{4}$/.test(text.slice(i + 1, i + 5))) fail();
          i += 5;
        } else if (text[i] !== undefined && '"\\/bfnrt'.includes(text[i])) i++;
        else fail();
        continue;
      }
      if (c < " ") fail();
      i++;
    }
    fail();
  };
  const NUMBER = /-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/y;
  const value = (): void => {
    ws();
    const c = text[i];
    if (c === "{" || c === "[") {
      const end = c === "{" ? "}" : "]";
      i++;
      ws();
      if (text[i] === end) {
        i++;
        return;
      }
      for (;;) {
        if (c === "{") {
          ws();
          if (text[i] !== '"') fail();
          string();
          ws();
          if (text[i] !== ":") fail();
          i++;
        }
        value();
        ws();
        if (text[i] === ",") {
          i++;
          continue;
        }
        if (text[i] === end) {
          i++;
          return;
        }
        fail();
      }
    }
    if (c === '"') return string();
    for (const literal of ["true", "false", "null"]) {
      if (text.startsWith(literal, i)) {
        i += literal.length;
        return;
      }
    }
    NUMBER.lastIndex = i;
    if (NUMBER.exec(text)) {
      i = NUMBER.lastIndex;
      return;
    }
    fail();
  };
  try {
    value();
    ws();
    if (i < text.length) fail();
    return -1;
  } catch (at) {
    // A draft nested past the stack's depth: no place to tell.
    return typeof at === "number" ? at : 0;
  }
}

export type ParsedDraft =
  | { ok: true; draft: Draft }
  | { ok: false; line: number | null; column: number | null; notObject?: true };

/** The editor's text as a draft, or where it goes wrong (line and column from 1). */
export function parseDraftText(text: string): ParsedDraft {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    const at = Math.max(0, jsonErrorLocation(text));
    const before = text.slice(0, at);
    const line = before.split("\n").length;
    return { ok: false, line, column: at - (before.lastIndexOf("\n") + 1) + 1 };
  }
  return isObject(value) ? { ok: true, draft: value } : { ok: false, line: null, column: null, notObject: true };
}

function sameJson(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (Array.isArray(a) || Array.isArray(b)) {
    return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((v, i) => sameJson(v, b[i]));
  }
  if (isObject(a) && isObject(b)) {
    const keys = Object.keys(a);
    return keys.length === Object.keys(b).length && keys.every((k) => k in b && sameJson(a[k], b[k]));
  }
  return false;
}

/** The first read-only section `edited` changed from `loaded` (one added or left out counts), or null. */
export function changedReadonlySection(loaded: Draft, edited: Draft, sections: readonly string[]): string | null {
  for (const section of sections) {
    const before = Object.prototype.hasOwnProperty.call(loaded, section);
    const after = Object.prototype.hasOwnProperty.call(edited, section);
    if (before !== after || (before && !sameJson(loaded[section], edited[section]))) return section;
  }
  return null;
}

/**
 * The draft to save: the user's sections, and the read-only ones as the
 * server's draft has them now. They are the same as the text's unless the
 * user chose to keep editing over a newer draft, whose change log (only the
 * server writes it) has grown since the text was read.
 */
export function withServerSections(edited: Draft, server: Draft, sections: readonly string[]): Draft {
  const out: Draft = { ...edited };
  for (const section of sections) {
    if (Object.prototype.hasOwnProperty.call(server, section)) out[section] = server[section];
    else delete out[section];
  }
  return out;
}

/** `<use_case.id>.blueprint.json`, with only safe characters in the id. */
export function blueprintFileName(draft: Draft): string {
  const useCase = isObject(draft.use_case) ? draft.use_case : {};
  const id = typeof useCase.id === "string" && useCase.id.trim() ? useCase.id.trim() : "blueprint";
  return `${id.replace(/[^A-Za-z0-9._-]+/g, "_")}.blueprint.json`;
}
