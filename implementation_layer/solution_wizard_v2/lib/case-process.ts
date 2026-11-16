/**
 * The generated solution as a process (cases): roles, screens and the review
 * form, all derived from what the wizard already produced. The BPMN gives the
 * roles (lanes holding a user task), the order of the steps and the review
 * decision; `target_output_spec` gives the form. Nothing here is written for
 * one use case.
 */

export type ProcessLane = { id: string; name: string; human: boolean };
export type ProcessNode = {
  id: string;
  kind: string;
  name: string;
  lane: string | null;
  inputs: (string | null)[];
  outputs: (string | null)[];
};
export type ProcessFlow = { from: string; to: string; name: string };
export type Process = { lanes: ProcessLane[]; nodes: ProcessNode[]; flows: ProcessFlow[] };

/** `target_output_spec` as wizard_api serves it (snake_case, V1 shape). */
export type OutputSpec = {
  schema_name?: string;
  fields: string[];
  field_types?: Record<string, string>;
  required_fields?: string[];
  field_descriptions?: Record<string, string>;
  allowed_values?: Record<string, string[]>;
};

export type CaseModel = {
  title: string;
  spec: OutputSpec;
  process: Process;
  /** The review task's id, decided by the api from the BPMN; null when nobody reviews. */
  reviewer?: string | null;
  package_ready: boolean;
  package_problems: string[];
  /** The file types an input upload accepts (absent from an older api). */
  accepted_inputs?: { kind?: string; label: string; extensions: string[] }[];
};

export type CaseStatus =
  | "draft"
  | "running"
  | "review"
  | "returned"
  | "approved"
  | "rejected"
  | "failed"
  | "completed";

export type CaseRecord = Record<string, unknown>;

export type Case = {
  id: string;
  created_at: string;
  status: CaseStatus;
  round: number;
  note: string;
  comment: string;
  run_id: string | null;
  run_phase?: string;
  run_message: string | null;
  inputs: { name: string; bytes: number; task?: string | null }[];
  steps_done?: string[];
  input_tasks?: Record<string, string>;
  notes?: Record<string, string>;
  return_to?: string | null;
  /** It came back to its input to be run again, by the person's own choice, not a reviewer's return. */
  rerun?: boolean;
  result: {
    record: CaseRecord | CaseRecord[] | null;
    /** The grounding check's file as the run wrote it; `hallucination_flags` names the values (lib/case-value). */
    validation: { passed?: boolean; hallucination_flags?: unknown } | null;
    transcript: string;
    document?: string;
    files: string[];
  } | null;
  record: CaseRecord | CaseRecord[] | null;
  events: { at: string; role: string; action: string; detail: string }[];
};

/** The name of a gateway's approving branch; the Workflow tab's flow view reads it too. */
export const APPROVE_FLOW = /^(yes|kyllä|approved?|hyväksytty)$/i;
const YES = APPROVE_FLOW;

export const isHumanTask = (n?: ProcessNode) =>
  !!n && (n.kind === "userTask" || n.kind === "manualTask");
export const isTask = (n?: ProcessNode) => !!n && /Task$|^task$/.test(n.kind);

/**
 * The parts of the process the UI needs: the steps in order (following the
 * approve branch at a gateway), the first user task (who gives the input), the
 * review task after it, and the roles.
 */
export function shapeProcess(process: Process, reviewer?: string | null) {
  const byId = new Map(process.nodes.map((n) => [n.id, n]));
  const out = (id: string) => process.flows.filter((f) => f.from === id);
  const start = process.nodes.find((n) => n.kind === "startEvent");
  const steps: ProcessNode[] = [];
  const seen = new Set<string>();
  let id = start?.id;
  while (id && !seen.has(id)) {
    seen.add(id);
    const node = byId.get(id);
    if (isTask(node)) steps.push(node as ProcessNode);
    const next = out(id);
    id = (next.find((f) => YES.test(f.name)) ?? next[0])?.to;
  }
  // Everyone before the first AI step gives a part of the input, in order;
  // the first person after an AI step reviews.
  const firstAi = steps.findIndex((n) => !isHumanTask(n));
  const inputTasks = (firstAi < 0 ? steps : steps.slice(0, firstAi)).filter(isHumanTask);
  const inputTask = inputTasks[0];
  // The api decides who reviews (its /cases/model says `reviewer`), so the
  // server and this screen cannot disagree and leave a case in review with no
  // review screen (#296). The rule below is the same, kept for an api that
  // does not say.
  const named = reviewer ? byId.get(reviewer) : undefined;
  const reviewTask =
    reviewer !== undefined
      ? isHumanTask(named)
        ? named
        : undefined
      : firstAi < 0
        ? undefined
        : steps.slice(firstAi).find(isHumanTask);
  const roles = process.lanes.filter((l) => l.human);
  const aiSteps = steps.filter((n) => !isHumanTask(n));
  return { steps, inputTask, inputTasks, reviewTask, roles, aiSteps, byId };
}

export type ShapedProcess = ReturnType<typeof shapeProcess>;

const isInputStatus = (status: CaseStatus) =>
  status === "draft" || status === "returned" || status === "failed";

/** The task a case is waiting on: the first input step not done yet, or the review. */
export function currentTask(
  shaped: ShapedProcess,
  status: CaseStatus,
  stepsDone: string[] = [],
): ProcessNode | undefined {
  if (isInputStatus(status)) {
    return shaped.inputTasks.find((n) => !stepsDone.includes(n.id)) ?? shaped.inputTasks.at(-1);
  }
  if (status === "review") return shaped.reviewTask;
  return undefined;
}

/** Whether the task is the last input step, the one that sends the case to the AI. */
export const isLastInput = (shaped: ShapedProcess, node?: ProcessNode) =>
  !!node && shaped.inputTasks.at(-1)?.id === node.id;

/** Which steps are done, for the stepper. */
export function stepState(
  shaped: ShapedProcess,
  status: CaseStatus,
  node: ProcessNode,
  stepsDone: string[] = [],
): "done" | "current" | "todo" {
  const order = shaped.steps.indexOf(node);
  const inputAt = shaped.steps.indexOf(shaped.inputTasks.at(-1) as ProcessNode);
  // Nobody reviews: everything after the input is the run. With -1 here a
  // running case showed no step as current at all.
  const reviewIndex = shaped.steps.indexOf(shaped.reviewTask as ProcessNode);
  const reviewAt = reviewIndex < 0 ? Number.POSITIVE_INFINITY : reviewIndex;
  if (status === "approved" || status === "completed") return "done";
  if (isInputStatus(status)) {
    // The current task first: a failed run leaves its last input step among
    // the done ones, and the view asks for that input again.
    if (node === currentTask(shaped, status, stepsDone)) return "current";
    return stepsDone.includes(node.id) ? "done" : "todo";
  }
  if (status === "running")
    return order <= inputAt ? "done" : order < reviewAt ? "current" : "todo";
  if (status === "review")
    return order < reviewAt ? "done" : order === reviewAt ? "current" : "todo";
  return order <= reviewAt ? "done" : "todo"; // rejected
}

export type StepSegment = {
  key: string;
  /** A person's step stands alone; the AI's steps in a row are one segment. */
  human: boolean;
  nodes: ProcessNode[];
  state: "done" | "current" | "todo";
};

/**
 * The stepper's segments. Six boxes in a row, four of them "GAIK AI system",
 * scrolled sideways and said the same thing four times; a person trying the
 * solution needs to see whose turn it is and that the AI's part lies between.
 * So each human step is a segment, and each run of AI steps is one segment
 * that names its steps.
 */
export function stepSegments(
  shaped: ShapedProcess,
  status: CaseStatus,
  stepsDone: string[] = [],
): StepSegment[] {
  const segments: StepSegment[] = [];
  for (const node of shaped.steps) {
    const human = isHumanTask(node);
    const state = stepState(shaped, status, node, stepsDone);
    const last = segments.at(-1);
    if (!human && last && !last.human) {
      last.nodes.push(node);
      // Part done and part to do is a run that is under way.
      if (last.state !== state) last.state = "current";
      continue;
    }
    segments.push({ key: node.id, human, nodes: [node], state });
  }
  return segments;
}

// -- the review form -------------------------------------------------------------

const FORMATS: Record<string, RegExp> = {
  "DD/MM/YYYY": /^(0[1-9]|[12]\d|3[01])\/(0[1-9]|1[0-2])\/\d{4}$/,
  "YYYY-MM-DD": /^\d{4}-\d{2}-\d{2}$/,
  "HH:MM": /^([01]\d|2[0-3]):[0-5]\d$/,
};

export const formatOf = (spec: OutputSpec, field: string) =>
  Object.keys(FORMATS).find((k) => (spec.field_descriptions?.[field] ?? "").includes(k));
export const isList = (spec: OutputSpec, field: string) =>
  /^list/.test(spec.field_types?.[field] ?? "");
export const uncertainField = (spec: OutputSpec) =>
  spec.fields.find((f) => /uncertain/.test(f) && isList(spec, f));
/** `incident_location` and `dueDate` read as "Incident location" and "Due date".
 * The one labelling of an output field, for the case view and the PoC tab alike. */
export const humanize = (field: string): string => {
  const words = field
    .replace(/[_-]+/g, " ")
    .replace(/([a-z0-9])([A-Z])/g, (_, a: string, b: string) => `${a} ${b.toLowerCase()}`)
    .trim();
  return words ? words[0].toUpperCase() + words.slice(1) : field;
};
/** A value as one readable string: lists of plain values on one line, nested data as JSON. */
export const show = (v: unknown): string => {
  if (v === null || v === undefined) return "";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v) && v.every((x) => x === null || typeof x !== "object")) {
    return v.map(show).join(", ");
  }
  return JSON.stringify(v, null, 2);
};

export type FieldProblem = { kind: "required" | "allowed" | "format"; detail?: string };

/** The same checks wizard_api makes before it accepts an approval. */
export function fieldProblem(spec: OutputSpec, record: CaseRecord, field: string): FieldProblem | null {
  return valueProblem(spec, field, record[field]);
}

function valueProblem(spec: OutputSpec, field: string, value: unknown): FieldProblem | null {
  // An empty list is a value given ("no citations"); missing is null or blank text.
  const empty = value == null || (!Array.isArray(value) && show(value).trim() === "");
  if ((spec.required_fields ?? []).includes(field) && empty) return { kind: "required" };
  if (empty || typeof value !== "string") return null;
  const allowed = spec.allowed_values?.[field];
  if (allowed && !allowed.includes(value)) return { kind: "allowed", detail: allowed.join(", ") };
  const fmt = formatOf(spec, field);
  if (fmt && !FORMATS[fmt].test(value)) return { kind: "format", detail: fmt };
  return null;
}

/** The top-level fields; a dotted field (`line_item.article_code`) is a column of a table field. */
export const formFields = (spec: OutputSpec) => {
  const unc = uncertainField(spec);
  return spec.fields.filter((f) => f !== unc && !f.includes("."));
};

/** The list field a dotted field belongs to: `line_item.x` → `line_items`. */
function tableOf(prefix: string, record: CaseRecord): string {
  return [prefix, `${prefix}s`, `${prefix}es`].find((n) => Array.isArray(record[n])) ?? prefix;
}

export type RowProblem = { table: string; row: number; column: string; problem: FieldProblem };

/** The columns the spec names (`table.column`), checked on every row of their table. */
export function rowProblems(spec: OutputSpec, record: CaseRecord): RowProblem[] {
  const found: RowProblem[] = [];
  for (const field of spec.fields.filter((f) => f.includes("."))) {
    const [prefix, column] = [field.slice(0, field.indexOf(".")), field.slice(field.indexOf(".") + 1)];
    const table = tableOf(prefix, record);
    const rows = record[table];
    if (!Array.isArray(rows)) continue;
    rows.forEach((row, i) => {
      if (!row || typeof row !== "object") return;
      const problem = valueProblem(spec, field, (row as CaseRecord)[column]);
      if (problem) found.push({ table, row: i + 1, column, problem });
    });
  }
  return found;
}

export function problemCount(spec: OutputSpec, record: CaseRecord | CaseRecord[]): number {
  if (Array.isArray(record)) return record.reduce((n, r) => n + problemCount(spec, r), 0);
  return (
    formFields(spec).filter((f) => fieldProblem(spec, record, f)).length +
    rowProblems(spec, record).length
  );
}

/** A list of objects (participants, decisions…): edited as a table, not as text. */
export const isTable = (v: unknown): v is CaseRecord[] =>
  Array.isArray(v) && v.length > 0 && v.every((x) => !!x && typeof x === "object" && !Array.isArray(x));

/** The columns of a table value: every key any row has, in first-seen order. */
export function tableColumns(rows: CaseRecord[]): string[] {
  const cols: string[] = [];
  for (const r of rows) for (const k of Object.keys(r)) if (!cols.includes(k)) cols.push(k);
  return cols;
}

/** A cell or value that is itself structured is shown and edited as JSON. */
export const isStructured = (v: unknown) => v !== null && typeof v === "object";

/** The value a form input produced, in the record's own type. */
export function parseInput(spec: OutputSpec, field: string, raw: string): unknown {
  const text = raw.trim();
  if (text === "") return null;
  return isList(spec, field)
    ? text.split(",").map((s) => s.trim()).filter(Boolean)
    : text;
}

export function toCsv(record: CaseRecord | CaseRecord[]): string {
  const rows = Array.isArray(record) ? record : [record];
  const keys = tableColumns(rows);
  const cell = (v: unknown) => (isStructured(v) && !(Array.isArray(v) && v.every((x) => typeof x !== "object")) ? JSON.stringify(v) : show(v));
  // A cell that starts like a formula runs as one in Excel, and these cells are
  // AI output built on what someone uploaded (#298): a quote in front keeps it text.
  // A number (also one written as text, like "-2") is a value, not a formula,
  // and must stay a number in the sheet.
  const text = (v: unknown) => {
    const t = cell(v);
    if (typeof v === "number" || typeof v === "boolean") return t;
    if (/^[-+]?\d+([.,]\d+)?$/.test(t)) return t;
    return /^[=+\-@\t\r]/.test(t) ? `'${t}` : t;
  };
  const q = (v: unknown) => `"${text(v).replace(/"/g, '""')}"`;
  // The header row is named by the AI too, so it gets the same treatment.
  return "\ufeff" + [keys.map(q).join(","), ...rows.map((r) => keys.map((k) => q(r[k])).join(","))].join("\n") + "\n";
}

/**
 * Whether an input data object is audio, so the screen offers recording.
 * Whole words only: "Invoice Pdf" contains "voice" and locked the picker of an
 * invoice flow to audio files (customer finding, 8 Oct 2026). camelCase is
 * split first, so "incidentAudio" still counts; the Finnish "puhe" stem skips
 * puhelin, puhelu and puheen-, which are not speech.
 */
export const isAudioInput = (name: string | null) => {
  const words = (name ?? "").replace(/(\p{Ll})(\p{Lu})/gu, "$1 $2");
  return /(?<!\p{L})(?:audio|voice|recording|ääni|puhe(?!lin|lu|en))/iu.test(words);
};

// -- a document result (a generated report) --------------------------------------

type Section = { id?: string; title?: string; text?: string };

/** A result made of sections of text (a report) rather than a flat record. */
export function isDocument(record: CaseRecord | CaseRecord[] | null | undefined): boolean {
  if (!record || Array.isArray(record)) return false;
  const sections = record.sections;
  return (
    Array.isArray(sections) &&
    sections.length > 0 &&
    sections.every((x) => !!x && typeof x === "object" && "text" in (x as object))
  );
}

/** The report as Markdown: title, then each section under its own heading. */
export function toMarkdown(record: CaseRecord): string {
  const parts: string[] = [];
  if (typeof record.title === "string") parts.push(`# ${record.title}`);
  for (const sec of (record.sections as Section[]) ?? []) {
    parts.push(`## ${sec.title ?? sec.id ?? ""}`.trimEnd(), String(sec.text ?? "").trim());
  }
  return parts.join("\n\n") + "\n";
}
