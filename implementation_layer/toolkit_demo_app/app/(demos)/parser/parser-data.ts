// What the Parser demo works with: ready-made documents, and what can be read
// out of the markdown a parser returns (blocks, headings, statistics, matches).

import type { ParserType } from "../extractor/extractor-data";

export interface ParserExample {
  id: string;
  title: string;
  summary: string;
  url: string;
  fileName: string;
  /** The parser that reads this document best. */
  parser: ParserType;
  /** Why that parser, for the card. */
  why: string;
}

export const EXAMPLES: ParserExample[] = [
  {
    id: "test-document",
    title: "GAIK test document",
    summary:
      "A one-page site safety report: details, a checklist of ticked boxes, findings and signatures.",
    url: "/vision-extractor-example/site-safety-inspection.pdf",
    fileName: "site-safety-inspection.pdf",
    parser: "docling_api",
    why: "HH Parser keeps headings and tables",
  },
  {
    id: "application",
    title: "Employment application form",
    summary: "A two-page form with handwriting, ticked boxes and tables.",
    url: "/vision-extractor-example/employment-application.pdf",
    fileName: "employment-application.pdf",
    parser: "docling_api",
    why: "HH Parser keeps the form tables",
  },
  {
    id: "lease",
    title: "Rental agreement",
    summary: "A one-page contract with key terms and a table of charges.",
    url: "/extractor-examples/rental-agreement.pdf",
    fileName: "rental-agreement.pdf",
    parser: "docling_api",
    why: "Compare HH Parser with PyMuPDF",
  },
  {
    id: "receipt",
    title: "Shop receipt (photo)",
    summary:
      "A tilted photo of a Finnish receipt: an image, with no text layer.",
    url: "/vision-extractor-example/receipt.jpg",
    fileName: "receipt.jpg",
    parser: "vision",
    why: "Vision reads text from an image",
  },
];

// ---------------------------------------------------------------------------
// Markdown
// ---------------------------------------------------------------------------

export type Inline =
  | { t: "text"; text: string }
  | { t: "bold"; text: string }
  | { t: "italic"; text: string }
  | { t: "code"; text: string }
  | { t: "link"; text: string; href: string };

export type Block =
  | { type: "heading"; level: number; text: string; id: string }
  | { type: "paragraph"; text: string }
  | { type: "code"; lang: string; text: string }
  | {
      type: "list";
      ordered: boolean;
      items: { text: string; depth: number }[];
    }
  | { type: "table"; header: string[]; rows: string[][] }
  | { type: "quote"; text: string }
  | { type: "hr" };

const isTableSeparator = (line: string): boolean =>
  /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(line) &&
  line.includes("-") &&
  line.includes("|");

function splitRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((cell) => cell.trim());
}

/** The markdown as blocks: headings, paragraphs, lists, tables, code, quotes. */
export function parseBlocks(markdown: string): Block[] {
  const lines = markdown.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let headings = 0;
  let i = 0;

  const startsBlock = (line: string): boolean =>
    /^\s{0,3}(#{1,6})\s/.test(line) ||
    /^\s*```/.test(line) ||
    /^\s*([-*+]|\d+[.)])\s/.test(line) ||
    /^\s*>/.test(line) ||
    /^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line) ||
    line.includes("|");

  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === "" || /^\s*<!--.*-->\s*$/.test(line)) {
      i += 1;
      continue;
    }

    const fence = line.match(/^\s*```\s*(\S*)/);
    if (fence) {
      const body: string[] = [];
      i += 1;
      while (i < lines.length && !/^\s*```/.test(lines[i])) {
        body.push(lines[i]);
        i += 1;
      }
      i += 1;
      blocks.push({ type: "code", lang: fence[1], text: body.join("\n") });
      continue;
    }

    const heading = line.match(/^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/);
    if (heading) {
      blocks.push({
        type: "heading",
        level: heading[1].length,
        text: heading[2],
        id: `md-h-${headings}`,
      });
      headings += 1;
      i += 1;
      continue;
    }

    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      blocks.push({ type: "hr" });
      i += 1;
      continue;
    }

    if (
      line.includes("|") &&
      i + 1 < lines.length &&
      isTableSeparator(lines[i + 1])
    ) {
      const header = splitRow(line);
      const rows: string[][] = [];
      i += 2;
      while (
        i < lines.length &&
        lines[i].trim() !== "" &&
        lines[i].includes("|")
      ) {
        rows.push(splitRow(lines[i]));
        i += 1;
      }
      blocks.push({ type: "table", header, rows });
      continue;
    }

    if (/^\s*>/.test(line)) {
      const body: string[] = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) {
        body.push(lines[i].replace(/^\s*>\s?/, ""));
        i += 1;
      }
      blocks.push({ type: "quote", text: body.join(" ") });
      continue;
    }

    const item = line.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
    if (item) {
      const ordered = /\d/.test(item[2]);
      const items: { text: string; depth: number }[] = [];
      while (i < lines.length) {
        const next = lines[i].match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
        if (!next) break;
        items.push({
          text: next[3],
          depth: Math.min(3, Math.floor(next[1].length / 2)),
        });
        i += 1;
      }
      blocks.push({ type: "list", ordered, items });
      continue;
    }

    const paragraph: string[] = [line.trim()];
    i += 1;
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !startsBlock(lines[i])
    ) {
      paragraph.push(lines[i].trim());
      i += 1;
    }
    blocks.push({ type: "paragraph", text: paragraph.join(" ") });
  }
  return blocks;
}

const INLINE =
  /(!?\[([^\]]*)\]\(([^)\s]*)[^)]*\))|(\*\*([^*]+)\*\*)|(__([^_]+)__)|(`([^`]+)`)|(\*([^*\s][^*]*)\*)/g;

/** The inline marks of one line of text: bold, italic, code and links. */
export function parseInline(text: string): Inline[] {
  const out: Inline[] = [];
  let last = 0;
  for (const match of text.matchAll(INLINE)) {
    const start = match.index ?? 0;
    if (start > last) out.push({ t: "text", text: text.slice(last, start) });
    if (match[1]) {
      // An image shows its alt text; a link keeps its address.
      if (match[1].startsWith("!"))
        out.push({ t: "text", text: match[2] || "[image]" });
      else out.push({ t: "link", text: match[2] || match[3], href: match[3] });
    } else if (match[4]) out.push({ t: "bold", text: match[5] });
    else if (match[6]) out.push({ t: "bold", text: match[7] });
    else if (match[8]) out.push({ t: "code", text: match[9] });
    else if (match[10]) out.push({ t: "italic", text: match[11] });
    last = start + match[0].length;
  }
  if (last < text.length) out.push({ t: "text", text: text.slice(last) });
  return out;
}

/** The text without markdown marks, for the plain view. */
export function toPlainText(markdown: string): string {
  return parseBlocks(markdown)
    .map((block) => {
      const plain = (text: string) =>
        parseInline(text)
          .map((part) => part.text)
          .join("");
      switch (block.type) {
        case "heading":
          return plain(block.text);
        case "paragraph":
        case "quote":
          return plain(block.text);
        case "code":
          return block.text;
        case "list":
          return block.items
            .map(
              (entry, index) =>
                `${"  ".repeat(entry.depth)}${block.ordered ? `${index + 1}.` : "-"} ${plain(entry.text)}`,
            )
            .join("\n");
        case "table":
          return [block.header, ...block.rows]
            .map((row) => row.map(plain).join("\t"))
            .join("\n");
        case "hr":
          return "";
      }
    })
    .filter((text) => text !== "")
    .join("\n\n");
}

// ---------------------------------------------------------------------------
// What the output holds
// ---------------------------------------------------------------------------

export interface Outline {
  id: string;
  level: number;
  text: string;
}

export function outlineOf(blocks: Block[]): Outline[] {
  return blocks.flatMap((block) =>
    block.type === "heading"
      ? [
          {
            id: block.id,
            level: block.level,
            text: block.text.replace(/[*_`]/g, ""),
          },
        ]
      : [],
  );
}

export interface Stats {
  characters: number;
  words: number;
  lines: number;
  headings: number;
  tables: number;
  lists: number;
}

export function statsOf(text: string, blocks: Block[]): Stats {
  const trimmed = text.trim();
  return {
    characters: text.length,
    words: trimmed === "" ? 0 : trimmed.split(/\s+/).length,
    lines: trimmed === "" ? 0 : trimmed.split(/\r?\n/).length,
    headings: blocks.filter((block) => block.type === "heading").length,
    tables: blocks.filter((block) => block.type === "table").length,
    lists: blocks.filter((block) => block.type === "list").length,
  };
}

const escapeRegExp = (value: string): string =>
  value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Splits text at the matches of a query (case-insensitive), keeping both parts. */
export function splitByQuery(
  text: string,
  query: string,
): { text: string; hit: boolean }[] {
  const needle = query.trim();
  if (needle === "") return [{ text, hit: false }];
  const parts = text.split(new RegExp(`(${escapeRegExp(needle)})`, "gi"));
  return parts
    .filter((part) => part !== "")
    .map((part) => ({
      text: part,
      hit: part.toLowerCase() === needle.toLowerCase(),
    }));
}

export function countMatches(text: string, query: string): number {
  const needle = query.trim();
  if (needle === "") return 0;
  return text.match(new RegExp(escapeRegExp(needle), "gi"))?.length ?? 0;
}
