// What the Tabular Agent demo works with: ready-made data files with questions that show what
// the agent can do, and how the rows of an answer are sorted, charted and saved.

export interface ExampleQuestion {
  question: string;
  /** What it shows the agent doing. */
  shows: string;
}

export interface TabularExample {
  id: string;
  title: string;
  summary: string;
  tags: string[];
  /** The file in public/. */
  url: string;
  fileName: string;
  questions: ExampleQuestion[];
}

const DIR = "/tabular-examples";

export const EXAMPLES: TabularExample[] = [
  {
    id: "projects",
    title: "Construction projects: three sheets that belong together",
    summary:
      "A workbook with projects, their costs and their inspections. The questions need the sheets joined: costs against budgets, inspections against projects.",
    tags: ["3 sheets", "joins", "budgets and costs"],
    url: `${DIR}/construction-projects.xlsx`,
    fileName: "construction-projects.xlsx",
    questions: [
      {
        question: "Which project is the most over its budget, in percent?",
        shows: "joins Costs to Projects, sums, compares",
      },
      {
        question: "What share of the costs of each project is labour?",
        shows: "groups by project and category",
      },
      {
        question: "Which active projects have had a failed inspection?",
        shows: "filters across two sheets",
      },
      {
        question: "Which inspector has found the most issues in total?",
        shows: "sums and ranks",
      },
    ],
  },
  {
    id: "report",
    title: "A messy Finnish budget report",
    summary:
      "A report as people really write them: title rows, numbers like “12 450,00” stored as text, subtotals and a note at the bottom. The agent cleans it, and understands Finnish.",
    tags: ["Finnish", "messy layout", "Nordic numbers"],
    url: `${DIR}/kustannusraportti-2025.xlsx`,
    fileName: "kustannusraportti-2025.xlsx",
    questions: [
      {
        question: "Mikä kustannuspaikka ylitti budjetin eniten?",
        shows: "a question in Finnish, subtotals left out",
      },
      {
        question: "What was the total actual spend in the first quarter?",
        shows: "turns text numbers into numbers, and months into a quarter",
      },
      {
        question:
          "Show the months where Tuotekehitys exceeded its budget by more than 20 %.",
        shows: "a percentage filter on cleaned columns",
      },
    ],
  },
  {
    id: "tickets",
    title: "Support tickets: dates and gaps",
    summary:
      "180 tickets with opening and closing dates, a priority, response times and a satisfaction score that is often empty. Good for medians, trends and missing values.",
    tags: ["CSV", "dates", "missing values"],
    url: `${DIR}/support-tickets.csv`,
    fileName: "support-tickets.csv",
    questions: [
      {
        question: "What is the median first response time for each priority?",
        shows: "a median, which an average would hide",
      },
      {
        question: "How many tickets are still open, by category?",
        shows: "empty dates mean “still open”",
      },
      {
        question: "Which month had the most tickets opened?",
        shows: "groups dates by month",
      },
      {
        question:
          "Is the average satisfaction lower when the first response took more than 24 hours?",
        shows: "compares two groups and skips empty scores",
      },
    ],
  },
];

// ---------------------------------------------------------------------------
// Reading the rows of an answer
// ---------------------------------------------------------------------------

export type Row = Record<string, unknown>;

export const isNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);

/** The columns of a result, in the order they come. */
export const columnsOf = (rows: Row[]): string[] => Object.keys(rows[0] ?? {});

/** The rows sorted by a column: numbers as numbers, the rest as text, empty values last. */
export function sortRows(
  rows: Row[],
  column: string,
  descending: boolean,
): Row[] {
  const empty = (value: unknown) => value === null || value === undefined;
  return [...rows].sort((a, b) => {
    const x = a[column];
    const y = b[column];
    if (empty(x) || empty(y)) return Number(empty(x)) - Number(empty(y));
    const order =
      isNumber(x) && isNumber(y)
        ? x - y
        : String(x).localeCompare(String(y), undefined, { numeric: true });
    return descending ? -order : order;
  });
}

export interface Bar {
  label: string;
  value: number;
}

/**
 * A result of one text column and one number column, up to 24 rows, can be drawn as bars.
 * Null when the rows are not shaped like that.
 */
export function barsOf(
  rows: Row[],
): { labelColumn: string; valueColumn: string; bars: Bar[] } | null {
  const columns = columnsOf(rows);
  if (rows.length < 2 || rows.length > 24 || columns.length < 2) return null;
  const numeric = columns.filter((column) =>
    rows.every((row) => isNumber(row[column])),
  );
  const labels = columns.filter((column) => !numeric.includes(column));
  if (numeric.length === 0 || labels.length !== 1 || numeric.length !== 1)
    return null;
  return {
    labelColumn: labels[0],
    valueColumn: numeric[0],
    bars: rows.map((row) => ({
      label: String(row[labels[0]] ?? "–"),
      value: row[numeric[0]] as number,
    })),
  };
}

const cell = (value: unknown): string => {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
};

export function toCsv(rows: Row[]): string {
  const columns = columnsOf(rows);
  return [
    columns.map(cell).join(","),
    ...rows.map((row) => columns.map((column) => cell(row[column])).join(",")),
  ].join("\n");
}

export const percent = (fraction: number): string =>
  `${Math.round(fraction * 100)}%`;
