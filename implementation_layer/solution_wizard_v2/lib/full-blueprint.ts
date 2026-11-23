/**
 * The full blueprint view's logic (components/full-blueprint-view): the
 * draft as `GET /api/sessions/{id}/blueprint/full` answers it, its text in
 * the advanced editor, where the read-only sections stand in that text, and
 * the checks made before a save is sent (the JSON parses, it is an object, no
 * read-only section changed). wizard_api checks the same again.
 */
import { AI_RECORD_MARK } from "@/lib/ai-marking";

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

const hasKey = (draft: Draft, key: string) => Object.prototype.hasOwnProperty.call(draft, key);

/** Whether `key` is the same in both drafts: absent in both, or present with the same value. */
function sameSection(a: Draft, b: Draft, key: string): boolean {
  return hasKey(a, key) === hasKey(b, key) && (!hasKey(a, key) || sameJson(a[key], b[key]));
}

export type Merged = { ok: true; draft: Draft } | { ok: false; conflicts: string[] };

/**
 * The draft to save, section by section (the top-level keys): `old` is the
 * draft the editor's text was made from, `newer` the server's draft now (the
 * same as `old` until a save was refused as changed elsewhere and the user
 * kept editing), `mine` the parsed text. A section only one side changed
 * takes that side; one both changed alike takes it; one both changed
 * differently is a conflict, named in the answer, and nothing is saved. The
 * read-only sections are always the newer draft's: only the server writes them.
 */
export function mergeDrafts(old: Draft, newer: Draft, mine: Draft, readonly: readonly string[]): Merged {
  const keys = [...new Set([...Object.keys(newer), ...Object.keys(mine), ...Object.keys(old)])];
  const out: Draft = {};
  const conflicts: string[] = [];
  for (const key of keys) {
    let from: Draft;
    if (readonly.includes(key) || sameSection(mine, old, key)) from = newer;
    else if (sameSection(newer, old, key) || sameSection(newer, mine, key)) from = mine;
    else {
      conflicts.push(key);
      continue;
    }
    if (hasKey(from, key)) out[key] = from[key];
  }
  return conflicts.length > 0 ? { ok: false, conflicts } : { ok: true, draft: out };
}

/**
 * The draft as the downloaded file has it: marked as AI output first (EU AI
 * Act art. 50(2)), with the mark the case exports carry (lib/ai-marking).
 * `Blueprint` ignores the extra top-level keys; a save strips them anyway.
 */
export function downloadText(draft: Draft): string {
  return JSON.stringify({ ...AI_RECORD_MARK, ...withoutAiMark(draft) }, null, 2);
}

/** The draft without the download's AI mark: a file pasted back into the editor is saved without it. */
export function withoutAiMark(draft: Draft): Draft {
  const out: Draft = { ...draft };
  for (const key of Object.keys(AI_RECORD_MARK)) delete out[key];
  return out;
}

/** `<use_case.id>.blueprint.json`, with only safe characters in the id. */
export function blueprintFileName(draft: Draft): string {
  const useCase = isObject(draft.use_case) ? draft.use_case : {};
  const id = typeof useCase.id === "string" && useCase.id.trim() ? useCase.id.trim() : "blueprint";
  return `${id.replace(/[^A-Za-z0-9._-]+/g, "_")}.blueprint.json`;
}
