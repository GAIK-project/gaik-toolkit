// Data of the Web Scraper demo: the sites, the presets, the crawl state built from the
// backend's events, and the extracted records joined with their checked quotes.

export interface Site {
  id: string;
  label: string;
  url: string;
  domain: string;
  description: string;
}

export interface Preset {
  label: string;
  requirements: string;
}

// The backend owns the allowlist (GET /api/web-scraper/sites); this copy only lets
// the page render before that answer arrives.
export const DEFAULT_SITES: Site[] = [
  {
    id: "gaik",
    label: "GAIK project",
    url: "https://gaik.ai/",
    domain: "gaik.ai",
    description: "The project site: toolkit, use cases, news and events",
  },
  {
    id: "haaga-helia",
    label: "Haaga-Helia",
    url: "https://www.haaga-helia.fi/fi",
    domain: "haaga-helia.fi",
    description:
      "The university of applied sciences: degrees, research and news",
  },
];

export const PRESETS: Record<string, Preset[]> = {
  gaik: [
    {
      label: "Events & workshops",
      requirements:
        "List the upcoming events and workshops: title, date (YYYY-MM-DD), time and the source page URL.",
    },
    {
      label: "Toolkit components",
      requirements:
        "List the GAIK toolkit components and modules the pages describe: name, what it does in one sentence, and the source page URL.",
    },
    {
      label: "Consortium partners",
      requirements:
        "List the organisations in the project consortium: organisation name, whether it is a company or a university, and the source page URL.",
    },
  ],
  "haaga-helia": [
    {
      label: "Fields of study",
      requirements:
        "List the fields of study and degree programmes the pages mention: name, a short description in the language of the page, and the source page URL.",
    },
    {
      label: "News",
      requirements:
        "List the news items and announcements: headline, date (YYYY-MM-DD) and the source page URL.",
    },
    {
      label: "Services for companies",
      requirements:
        "List the services offered to companies: service name, a one-sentence description, and the source page URL.",
    },
  ],
};

export type NodeStatus = "fetching" | "page" | "skipped";

/** One URL of the crawl as the constellation and the page list show it. */
export interface CrawlNode {
  /** The URL as requested: the node's identity. */
  url: string;
  /** The URL after redirects; later events name a parent by this one. */
  finalUrl: string;
  parent: string | null;
  depth: number;
  status: NodeStatus;
  order: number;
  title?: string | null;
  description?: string | null;
  language?: string | null;
  published?: string | null;
  words?: number;
  links?: string[];
  externalLinks?: number;
  structuredDataTypes?: string[];
  markdown?: string;
  elapsed?: number;
  reason?: string;
}

export interface CrawlStats {
  pages: number;
  skipped: number;
  words: number;
  durationS: number;
}

export interface SchemaField {
  name: string;
  type?: string;
  description?: string;
  children?: SchemaField[];
}

export interface Citation {
  field: string;
  quote: string;
  value: unknown;
  verdict: "verified" | "reworded" | "check" | "unchecked";
  record: number | null;
  page_url: string | null;
}

export interface Extraction {
  records: Record<string, unknown>[];
  sources: Citation[];
  documentChars: number;
  model?: string | null;
}

export type Phase =
  | "idle"
  | "crawling"
  | "schema"
  | "extracting"
  | "done"
  | "error";

export interface RunState {
  phase: Phase;
  nodes: CrawlNode[];
  stats: CrawlStats | null;
  message: string | null;
  schema: SchemaField[] | null;
  extraction: Extraction | null;
  error: string | null;
}

export const INITIAL_STATE: RunState = {
  phase: "idle",
  nodes: [],
  stats: null,
  message: null,
  schema: null,
  extraction: null,
  error: null,
};

export type RunEvent =
  | { type: "start" }
  | { type: string; data: Record<string, unknown> };

function str(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

/** The node a URL names: by its requested or its final URL. */
export function findNode(
  nodes: CrawlNode[],
  url: string | null,
): CrawlNode | undefined {
  if (!url) return undefined;
  return nodes.find((node) => node.url === url || node.finalUrl === url);
}

/** The state after one event of the backend's stream. */
export function reduceRun(state: RunState, event: RunEvent): RunState {
  if (event.type === "start") return { ...INITIAL_STATE, phase: "crawling" };
  if (!("data" in event)) return state;
  const data = event.data;
  switch (event.type) {
    case "request": {
      const url = str(data.url);
      if (!url || findNode(state.nodes, url)) return state;
      const node: CrawlNode = {
        url,
        finalUrl: url,
        parent: str(data.parent_url),
        depth: Number(data.depth ?? 0),
        status: "fetching",
        order: state.nodes.length,
      };
      return { ...state, nodes: [...state.nodes, node] };
    }
    case "page": {
      const url = str(data.url);
      if (!url) return state;
      const page: Partial<CrawlNode> = {
        finalUrl: str(data.final_url) ?? url,
        status: "page",
        title: str(data.title),
        description: str(data.description),
        language: str(data.language),
        published: str(data.published),
        words: Number(data.word_count ?? 0),
        links: Array.isArray(data.links) ? (data.links as string[]) : [],
        externalLinks: Number(data.external_links ?? 0),
        structuredDataTypes: Array.isArray(data.structured_data_types)
          ? (data.structured_data_types as string[])
          : [],
        markdown: str(data.markdown) ?? "",
        elapsed: Number(data.elapsed_s ?? 0),
      };
      const existing = findNode(state.nodes, url);
      const nodes = existing
        ? state.nodes.map((node) =>
            node === existing ? { ...node, ...page } : node,
          )
        : [
            ...state.nodes,
            {
              url,
              parent: str(data.parent_url),
              depth: Number(data.depth ?? 0),
              order: state.nodes.length,
              ...page,
            } as CrawlNode,
          ];
      return { ...state, nodes };
    }
    case "skipped": {
      const url = str(data.url);
      if (!url) return state;
      const reason = str(data.reason) ?? "skipped";
      const existing = findNode(state.nodes, url);
      const nodes = existing
        ? state.nodes.map((node) =>
            node === existing
              ? { ...node, status: "skipped" as const, reason }
              : node,
          )
        : [
            ...state.nodes,
            {
              url,
              finalUrl: url,
              parent: str(data.parent_url),
              depth: Number(data.depth ?? 0),
              status: "skipped" as const,
              order: state.nodes.length,
              reason,
            },
          ];
      return { ...state, nodes };
    }
    case "crawl_done":
      return {
        ...state,
        // A redirect alias of a page already seen never gets a page event.
        nodes: state.nodes.filter((node) => node.status !== "fetching"),
        stats: {
          pages: Number(data.pages ?? 0),
          skipped: Number(data.skipped ?? 0),
          words: Number(data.words ?? 0),
          durationS: Number(data.duration_s ?? 0),
        },
        phase: "done",
      };
    case "progress":
      return {
        ...state,
        phase: data.stage === "schema" ? "schema" : "extracting",
        message: str(data.message),
      };
    case "schema":
      return {
        ...state,
        schema: Array.isArray(data.field_table)
          ? (data.field_table as SchemaField[])
          : null,
      };
    case "result":
      return {
        ...state,
        phase: "done",
        message: null,
        extraction: {
          records: Array.isArray(data.records)
            ? (data.records as Record<string, unknown>[])
            : [],
          sources: Array.isArray(data.sources)
            ? (data.sources as Citation[])
            : [],
          documentChars: Number(data.document_chars ?? 0),
          model: str(data.model),
        },
      };
    case "error":
      return {
        ...state,
        phase: "error",
        message: null,
        error: str(data.message) ?? "The run failed.",
      };
    default:
      return state;
  }
}

export interface Table {
  /** The key the rows were listed under, e.g. "events"; null for flat records. */
  key: string | null;
  columns: string[];
  rows: Record<string, unknown>[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** The extracted records as one table: the rows of the one list each result holds,
 * or the results themselves when they are flat. */
export function tableOf(records: Record<string, unknown>[]): Table {
  const rows: Record<string, unknown>[] = [];
  let key: string | null = null;
  for (const result of records) {
    const lists = Object.entries(result).filter(
      ([, value]) =>
        Array.isArray(value) && value.length > 0 && value.every(isRecord),
    );
    if (lists.length === 1) {
      key = lists[0][0];
      rows.push(...(lists[0][1] as Record<string, unknown>[]));
    } else {
      rows.push(result);
    }
  }
  const columns: string[] = [];
  for (const row of rows)
    for (const column of Object.keys(row))
      if (!columns.includes(column)) columns.push(column);
  return { key, columns, rows };
}

/** The citation of each cell, keyed ``row:column``. */
export function citationsByCell(sources: Citation[]): Map<string, Citation> {
  const cells = new Map<string, Citation>();
  for (const source of sources) {
    if (source.record === null || source.record === undefined) continue;
    const column = source.field
      .split(".")
      .pop()
      ?.replace(/\[\d+\]$/, "");
    if (!column) continue;
    const key = `${source.record}:${column}`;
    if (!cells.has(key)) cells.set(key, source);
  }
  return cells;
}

/** How many cited values each page holds, by the page's final URL. */
export function citationsPerPage(sources: Citation[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const source of sources)
    if (source.page_url)
      counts[source.page_url] = (counts[source.page_url] ?? 0) + 1;
  return counts;
}

/** The page most of a row's quotes come from. */
export function pageOfRow(sources: Citation[], row: number): string | null {
  const counts = citationsPerPage(
    sources.filter((source) => source.record === row),
  );
  const best = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
  return best ? best[0] : null;
}

/** A cell value as text. */
export function cellText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.map(cellText).join(", ");
  if (isRecord(value)) return JSON.stringify(value);
  return String(value);
}

export function isUrl(value: unknown): value is string {
  return typeof value === "string" && /^https?:\/\/\S+$/.test(value);
}

/** The crawled pages as one Markdown document, as gaik's CrawlResult.to_markdown(). */
export function crawlMarkdown(nodes: CrawlNode[]): string {
  return nodes
    .filter((node) => node.status === "page")
    .map(
      (node) =>
        `# ${node.title || node.finalUrl}\n\nSource: ${node.finalUrl}\n\n${node.markdown ?? ""}`.trimEnd() +
        "\n",
    )
    .join("\n---\n\n");
}

/** Whether a URL is inside one of the domains (a domain allows its subdomains). */
export function inDomains(url: string, domains: string[]): boolean {
  try {
    const parsed = new URL(url);
    if (!["http:", "https:"].includes(parsed.protocol)) return false;
    const host = parsed.hostname.toLowerCase();
    return domains.some(
      (domain) => host === domain || host.endsWith(`.${domain}`),
    );
  } catch {
    return false;
  }
}

/** A URL without its scheme, for compact labels. */
export function shortUrl(url: string): string {
  return url.replace(/^https?:\/\//, "").replace(/\/$/, "");
}
