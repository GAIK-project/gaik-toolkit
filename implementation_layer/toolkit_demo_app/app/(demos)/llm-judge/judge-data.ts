// What the LLM-as-Judge demo works with: ready-made cases with the verdict a person would
// expect, and how the verdicts are read, compared and applied.

export type Severity = "ok" | "suspect" | "wrong";

/** What a person would expect of a verdict: ok, wrong, or anything but ok. */
export type Expectation = "ok" | "wrong" | "not-ok";

export const SEVERITY_RANK: Record<Severity, number> = {
  ok: 0,
  suspect: 1,
  wrong: 2,
};

export function meets(expectation: Expectation, severity: Severity): boolean {
  if (expectation === "not-ok") return severity !== "ok";
  return severity === expectation;
}

export const EXPECTATION_TEXT: Record<Expectation, string> = {
  ok: "Expected: the same meaning (ok)",
  wrong: "Expected: clearly different (wrong)",
  "not-ok": "Expected: a real difference (suspect or wrong)",
};

// ---------------------------------------------------------------------------
// Text pairs (the Text pair and Panel modes)
// ---------------------------------------------------------------------------

export interface PairExample {
  id: string;
  title: string;
  summary: string;
  expected: string;
  extracted: string;
  fieldName: string;
  expect: Expectation;
}

export const PAIR_EXAMPLES: PairExample[] = [
  {
    id: "paraphrase",
    title: "A paraphrase",
    summary:
      "The words differ, the meaning is the same. A strict comparison fails it; a judge should not.",
    expected: "The computer was not locked.",
    extracted: "Computer left unlocked at the workstation.",
    fieldName: "incident_summary",
    expect: "ok",
  },
  {
    id: "finnish",
    title: "Finnish word forms",
    summary:
      "The same word in a different case. Text matching sees two words; a reader sees one.",
    expected: "kieppipeittaus",
    extracted: "kieppipeittauksessa",
    fieldName: "method",
    expect: "ok",
  },
  {
    id: "date",
    title: "A date, written another way",
    summary: "26.8.2025 and 2025-08-26 are the same day.",
    expected: "26.8.2025",
    extracted: "2025-08-26",
    fieldName: "report_date",
    expect: "ok",
  },
  {
    id: "number",
    title: "A number that is off",
    summary: "23 against 23.3. Close to the eye, wrong for a quantity.",
    expected: "23",
    extracted: "23.3",
    fieldName: "quantity",
    expect: "wrong",
  },
  {
    id: "different",
    title: "Two different things",
    summary: "The extractor found something unrelated to the reference.",
    expected: "Coolant leaked under unit B.",
    extracted: "Production output increased by 12 %.",
    fieldName: "finding",
    expect: "wrong",
  },
  {
    id: "subtle",
    title: "A near match with one wrong detail",
    summary:
      "A long entry where the time is 14:30 instead of 14:35. Judges may split here: that is what a panel is for.",
    expected:
      "Maintenance technician arrived at 14:35 and replaced the worn bearing on the conveyor. Belt tension re-adjusted; line restarted at 15:10. Root cause logged as bearing wear.",
    extracted:
      "Maintenance technician arrived at 14:30 and replaced the worn bearing on the conveyor. Belt tension was re-adjusted and the line restarted at 15:10. Cause: bearing wear.",
    fieldName: "maintenance_log_entry",
    expect: "not-ok",
  },
];

export interface DiffPart {
  text: string;
  kind: "same" | "removed" | "added";
}

/** The words of two texts side by side: what only the reference has, and what only the candidate has. */
export function wordDiff(expected: string, extracted: string): DiffPart[] {
  const a = expected.split(/\s+/).filter(Boolean);
  const b = extracted.split(/\s+/).filter(Boolean);
  const same = (x: string, y: string) => x.toLowerCase() === y.toLowerCase();
  // The longest common run of words, by the usual table.
  const table: number[][] = Array.from({ length: a.length + 1 }, () =>
    new Array<number>(b.length + 1).fill(0),
  );
  for (let i = a.length - 1; i >= 0; i -= 1)
    for (let j = b.length - 1; j >= 0; j -= 1)
      table[i][j] = same(a[i], b[j])
        ? table[i + 1][j + 1] + 1
        : Math.max(table[i + 1][j], table[i][j + 1]);
  const parts: DiffPart[] = [];
  const push = (text: string, kind: DiffPart["kind"]) => {
    const last = parts[parts.length - 1];
    if (last && last.kind === kind) last.text += ` ${text}`;
    else parts.push({ text, kind });
  };
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (same(a[i], b[j])) {
      push(b[j], "same");
      i += 1;
      j += 1;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      push(a[i], "removed");
      i += 1;
    } else {
      push(b[j], "added");
      j += 1;
    }
  }
  for (; i < a.length; i += 1) push(a[i], "removed");
  for (; j < b.length; j += 1) push(b[j], "added");
  return parts;
}

// ---------------------------------------------------------------------------
// Hallucinations
// ---------------------------------------------------------------------------

export interface HallucinationExample {
  id: string;
  title: string;
  summary: string;
  source: string;
  extracted: Record<string, unknown>;
  /** The fields that are not in the source. */
  invented: string[];
}

export const HALLUCINATION_EXAMPLES: HallucinationExample[] = [
  {
    id: "invented",
    title: "A report with two invented fields",
    summary:
      "The source says nothing of a priority or a follow-up date, yet the extractor filled both in.",
    source:
      "Maintenance round on 2025-09-12. The technician reported a coolant leak under unit B and applied an absorbent mat. The leak source was not identified during this visit.",
    extracted: {
      report_date: "2025-09-12",
      location: "unit B",
      issue_type: "coolant leak",
      actions_taken: "absorbent mat applied",
      priority: "high",
      follow_up_date: "2025-09-15",
    },
    invented: ["priority", "follow_up_date"],
  },
  {
    id: "grounded",
    title: "A report where every field is grounded",
    summary:
      "Each value can be found in the source. The judge should flag nothing.",
    source:
      "Site visit 26 March 2026 at Kometankuja 6. Inspector Jukka Lahtinen. Three roof tiles on the south slope are cracked and need replacing. Scaffolding on the north side has not been inspected.",
    extracted: {
      visit_date: "26 March 2026",
      site: "Kometankuja 6",
      inspector: "Jukka Lahtinen",
      cracked_tiles: "Three roof tiles on the south slope",
      scaffolding_inspected: "not inspected",
    },
    invented: [],
  },
];

export interface FlagLike {
  field: string;
  severity: Severity;
}

export interface Outcome {
  found: string[];
  missed: string[];
  extra: string[];
}

/** The flagged fields against the fields that were really invented. */
export function outcomeOf(flagged: string[], invented: string[]): Outcome {
  return {
    found: invented.filter((field) => flagged.includes(field)),
    missed: invented.filter((field) => !flagged.includes(field)),
    extra: flagged.filter((field) => !invented.includes(field)),
  };
}

export interface FieldRow {
  field: string;
  value: string;
  /** What the judge said, or "supported" for a field it did not flag. */
  status: Severity | "supported";
  reason: string | null;
}

const isEmpty = (value: unknown) =>
  value === null ||
  value === undefined ||
  (typeof value === "string" && value.trim() === "") ||
  (Array.isArray(value) && value.length === 0);

export function textOf(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value);
}

/** Every non-empty field of an object, with the judge's word on it. */
export function fieldRows(
  extracted: Record<string, unknown>,
  flags: { field: string; severity: Severity; reason: string }[],
): FieldRow[] {
  return Object.entries(extracted)
    .filter(([, value]) => !isEmpty(value))
    .map(([field, value]) => {
      const flag = flags.find((entry) => entry.field === field);
      return {
        field,
        value: textOf(value),
        status: flag ? flag.severity : "supported",
        reason: flag?.reason ?? null,
      };
    });
}

// ---------------------------------------------------------------------------
// Validating against a PDF
// ---------------------------------------------------------------------------

export interface ValidationFlagLike {
  item_index: number;
  field: string;
  severity: Severity;
  score: number;
  reason: string;
  suggested_value: string | null;
}

export interface GridRow {
  item: number;
  field: string;
  value: string;
  flag: ValidationFlagLike | null;
}

/** The items of an extraction as one list: an object is one item, indexed -1 like the judge does. */
export function itemsOf(
  extracted: unknown,
): { index: number; data: Record<string, unknown> }[] {
  if (Array.isArray(extracted))
    return extracted.flatMap((entry, index) =>
      entry && typeof entry === "object" && !Array.isArray(entry)
        ? [{ index, data: entry as Record<string, unknown> }]
        : [],
    );
  if (extracted && typeof extracted === "object")
    return [{ index: -1, data: extracted as Record<string, unknown> }];
  return [];
}

export function gridOf(
  extracted: unknown,
  flags: ValidationFlagLike[],
): GridRow[] {
  return itemsOf(extracted).flatMap(({ index, data }) =>
    Object.entries(data)
      .filter(([, value]) => !isEmpty(value))
      .map(([field, value]) => ({
        item: index,
        field,
        value: textOf(value),
        flag:
          flags.find((f) => f.item_index === index && f.field === field) ??
          null,
      })),
  );
}

/** The extraction with each suggested value put in place of the flagged one. */
export function applySuggestions(
  extracted: unknown,
  flags: ValidationFlagLike[],
): unknown {
  const copy = structuredClone(extracted);
  const fix = (target: Record<string, unknown>, flag: ValidationFlagLike) => {
    const suggestion = flag.suggested_value;
    if (suggestion === null || suggestion === undefined) return;
    const original = target[flag.field];
    const number = Number(suggestion.replace(/\s/g, "").replace(",", "."));
    target[flag.field] =
      typeof original === "number" && Number.isFinite(number)
        ? number
        : suggestion;
  };
  for (const flag of flags) {
    if (Array.isArray(copy)) {
      const item = copy[flag.item_index];
      if (item && typeof item === "object")
        fix(item as Record<string, unknown>, flag);
    } else if (copy && typeof copy === "object" && flag.item_index === -1) {
      fix(copy as Record<string, unknown>, flag);
    }
  }
  return copy;
}

export const INVOICE_EXAMPLE = {
  title: "An invoice with a wrong total",
  summary:
    "The extracted total_amount is the subtotal, not the grand total after discount and VAT. The judge should flag it and suggest 23901.62.",
  pdfUrl: "/invoice.pdf",
  pdfName: "invoice.pdf",
  extracted: {
    invoice_number: "INV-2026-00847",
    vendor: "Arctis Design",
    customer: "Nordwave Technologies Oy",
    date_issued: "2026-03-16",
    total_amount: 20290.0,
    currency: "EUR",
  },
  rubric: {
    field_checks: [
      "total_amount must equal the invoice's GRAND TOTAL (after discount and VAT), not the subtotal",
      "currency must be a 3-letter ISO code (e.g. EUR, USD)",
      "date_issued must be in ISO YYYY-MM-DD format",
    ],
  },
  wrongField: "total_amount",
  rightValue: "23901.62",
};

// ---------------------------------------------------------------------------
// Several judges
// ---------------------------------------------------------------------------

export interface JudgeVerdict {
  severity?: Severity;
  score?: number;
}

/** The verdict most judges gave; on a tie, the harshest. */
export function majority(verdicts: Severity[]): Severity | null {
  if (verdicts.length === 0) return null;
  const counts: Record<Severity, number> = { ok: 0, suspect: 0, wrong: 0 };
  for (const verdict of verdicts) counts[verdict] += 1;
  const top = Math.max(...Object.values(counts));
  return (Object.keys(counts) as Severity[])
    .filter((severity) => counts[severity] === top)
    .sort((x, y) => SEVERITY_RANK[y] - SEVERITY_RANK[x])[0];
}

export function median(scores: number[]): number | null {
  const valid = scores.filter((score) => score > 0).sort((x, y) => x - y);
  return valid.length ? valid[Math.floor((valid.length - 1) / 2)] : null;
}

export function agreementText(ratio: number): string {
  if (ratio >= 0.99) return "Unanimous: every judge agreed.";
  if (ratio >= 0.66) return "Strong agreement: most judges line up.";
  return "Mixed: treat the panel verdict as advice.";
}
