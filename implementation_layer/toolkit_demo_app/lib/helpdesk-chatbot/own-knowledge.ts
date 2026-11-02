// "Test on your own data": turn a user's own documents into a helpdesk's
// knowledge. Markdown, text, PDF and Word become FAQ articles (split at
// headings and questions); a CSV becomes the catalogue: the list of services,
// products or requests the helpdesk can tell about. No
// model is used here, so the same files always give the same knowledge.
//
// The browser builds the knowledge and sends it with each chat request, so
// nothing is stored on the server. The server validates it with
// `parseOwnKnowledge` before any model sees it: it comes from the user.

import { z } from "zod";
import type { HelpdeskExample } from "./examples";
import type { Article, Knowledge, Service } from "./knowledge";

/** The example id the chat sends when the knowledge is the user's own. */
export const OWN_ID = "own";

export const LIMITS = {
  documents: 8,
  articles: 200,
  services: 300,
  /** Longest article body, in characters. */
  articleChars: 2000,
  /** All text in the knowledge together, in characters. */
  totalChars: 150_000,
  organisationChars: 80,
} as const;

export type DocumentKind = "articles" | "catalogue";

/** One file, read. `warnings` are things the user should know about the reading. */
export interface LoadedDocument {
  name: string;
  kind: DocumentKind;
  articles: Article[];
  services: Service[];
  warnings: string[];
}

// ---------------------------------------------------------------------------
// Text, Markdown, PDF and Word: FAQ articles
// ---------------------------------------------------------------------------

function slug(text: string, max = 48): string {
  return (
    text
      .toLowerCase()
      .normalize("NFKD")
      .replace(/[^\p{L}\p{N}]+/gu, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, max) || "item"
  );
}

function baseName(fileName: string): string {
  return fileName.replace(/\.[^.]+$/, "");
}

function stripMarkdown(text: string): string {
  return text
    .replace(/[*_`~]+/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .trim();
}

const STOP_TAG_WORDS = new Set(
  "about after also and are can does for from have how into more not our that the their them then there these this what when where which will with you your".split(
    " ",
  ),
);

/** Search tags from a title: its longer words. */
function tagsFrom(title: string): string[] {
  const words = title.toLowerCase().match(/[\p{L}\p{N}]{4,}/gu) ?? [];
  return [...new Set(words.filter((w) => !STOP_TAG_WORDS.has(w)))].slice(0, 8);
}

function clip(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, max - 1).trimEnd()}…`;
}

function firstSentence(text: string, max = 70): string {
  const flat = text.replace(/\s+/g, " ").trim();
  const sentence = flat.match(/^.*?[.!?](\s|$)/)?.[0].trim() ?? flat;
  return clip(sentence.replace(/[.!?]$/, ""), max);
}

interface Section {
  title: string;
  body: string[];
}

const HEADING = /^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$/;

/** A short line that ends with a question mark and starts a paragraph: a FAQ question. */
function isQuestion(line: string, previous: string | undefined): boolean {
  return (
    previous !== undefined &&
    previous.trim() === "" &&
    /\?\s*$/.test(line) &&
    line.trim().length <= 140 &&
    !/^[-*•]/.test(line.trim())
  );
}

/** A line that looks like a title in plain text: short, capitalised, no full stop, not a "label: value" row. */
function isTitleLine(text: string): boolean {
  return (
    text.length >= 3 &&
    text.length <= 60 &&
    text.split(/\s+/).length <= 8 &&
    !/[.,;:!?)"”]$/.test(text) &&
    !/:\s/.test(text) &&
    /^[\p{Lu}\p{N}]/u.test(text) &&
    !/^[-*•]/.test(text)
  );
}

/** A line of running text or a list item, as opposed to a label or a table cell. */
function isTextLine(text: string): boolean {
  return text.length >= 20 && !/^[-*•]/.test(text);
}

function sectionsByTitleLines(lines: string[]): Section[] {
  const sections: Section[] = [];
  let current: Section = { title: "", body: [] };
  let afterTitle = false;
  // A line that comes back again and again ("In stock", "Specifications") is
  // a label or a table cell, not the title of one article.
  const counts = new Map<string, number>();
  for (const l of lines) {
    const t = l.trim();
    if (t) counts.set(t, (counts.get(t) ?? 0) + 1);
  }
  const nextLines = (index: number) =>
    lines
      .slice(index + 1)
      .map((l) => l.trim())
      .filter(Boolean);
  // A title has text under it, or a title of its own that has (a group name
  // above a title). Labels such as the header of a table do not.
  const hasTextUnder = (index: number) => {
    const [first, second] = nextLines(index);
    if (first === undefined) return false;
    if (isTextLine(first)) return true;
    return isTitleLine(first) && second !== undefined && isTextLine(second);
  };

  lines.forEach((line, index) => {
    const text = line.trim();
    const previous = lines[index - 1]?.trim();
    // A new paragraph follows a blank line, a sentence end, a title or a short
    // line such as a table cell; a wrapped line of running text is longer.
    const startsParagraph =
      previous === undefined ||
      previous === "" ||
      /[.!?:;)"”]$/.test(previous) ||
      previous.length <= 20 ||
      afterTitle;
    if (
      text &&
      isTitleLine(text) &&
      (counts.get(text) ?? 0) < 3 &&
      startsParagraph &&
      hasTextUnder(index)
    ) {
      sections.push(current);
      current = { title: text, body: [] };
      afterTitle = true;
    } else {
      current.body.push(line);
      if (text) afterTitle = false;
    }
  });
  sections.push(current);
  return sections;
}

/**
 * FAQ articles from running text. A Markdown heading or a question on a line
 * of its own starts a new article; in plain text so does a short title line.
 * Text with none of these is cut at blank lines, with short paragraphs joined
 * to the next one.
 */
export function articlesFromText(text: string, fileName: string): Article[] {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const sections: Section[] = [];
  let current: Section = { title: "", body: [] };
  let sawHeading = false;

  lines.forEach((line, index) => {
    const heading = line.match(HEADING);
    if (
      heading ||
      isQuestion(line, lines[index - 1] ?? (index === 0 ? "" : undefined))
    ) {
      sections.push(current);
      current = {
        title: stripMarkdown(heading ? heading[1] : line.trim()),
        body: [],
      };
      sawHeading = true;
    } else {
      current.body.push(line);
    }
  });
  sections.push(current);

  const name = baseName(fileName);
  const articles: Article[] = [];
  const add = (title: string, body: string, group = "") => {
    const clean = body.replace(/\n{3,}/g, "\n\n").trim();
    if (clean.length < 20) return;
    const heading = title || firstSentence(clean);
    articles.push({
      id: `${slug(name, 24)}-${articles.length + 1}-${slug(heading, 24)}`,
      title: clip(heading, 120),
      body: clip(clean, LIMITS.articleChars),
      tags: tagsFrom(`${heading} ${group} ${name}`),
    });
  };

  if (sawHeading) {
    for (const section of sections) add(section.title, section.body.join("\n"));
    return articles;
  }

  // No Markdown headings or questions, as when a PDF or Word file is read as
  // plain text: a short line without a full stop that starts a paragraph is a
  // title. A short title with nothing under it (a chapter or category name)
  // is not an article of its own: its words become search tags of the titles
  // that follow it, so a search for the group still finds them.
  const titled = sectionsByTitleLines(lines);
  if (titled.filter((s) => s.title).length >= 2) {
    let parent = "";
    for (const section of titled) {
      if (section.body.join("\n").trim().length < 20) {
        parent = section.title.length <= 30 ? section.title : "";
        continue;
      }
      add(section.title, section.body.join("\n"), parent);
    }
    return articles;
  }

  // No headings: paragraphs, with short ones joined to the next.
  const paragraphs = text
    .replace(/\r\n?/g, "\n")
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);
  let carry = "";
  for (const paragraph of paragraphs) {
    const joined = carry ? `${carry}\n\n${paragraph}` : paragraph;
    if (joined.length < 80) {
      carry = joined;
      continue;
    }
    add("", joined);
    carry = "";
  }
  if (carry) add("", carry);
  return articles;
}

// ---------------------------------------------------------------------------
// CSV: products or services
// ---------------------------------------------------------------------------

/** Rows of a CSV, with quotes and the delimiter (comma, semicolon or tab) found from the first line. */
export function parseCsv(text: string): string[][] {
  const clean = text.replace(/^﻿/, "");
  const first = clean.split(/\r?\n/, 1)[0] ?? "";
  const delimiter =
    ([",", ";", "\t"] as const)
      .map((d) => [d, first.split(d).length] as const)
      .sort((a, b) => b[1] - a[1])[0][0] ?? ",";

  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < clean.length; i++) {
    const ch = clean[i];
    if (quoted) {
      if (ch === '"' && clean[i + 1] === '"') {
        cell += '"';
        i++;
      } else if (ch === '"') quoted = false;
      else cell += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === delimiter) {
      row.push(cell);
      cell = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && clean[i + 1] === "\n") i++;
      row.push(cell);
      cell = "";
      if (row.some((c) => c.trim() !== "")) rows.push(row.map((c) => c.trim()));
      row = [];
    } else cell += ch;
  }
  row.push(cell);
  if (row.some((c) => c.trim() !== "")) rows.push(row.map((c) => c.trim()));
  return rows;
}

const COLUMNS = {
  name: [
    "name",
    "product",
    "product_name",
    "title",
    "item",
    "service",
    "tuote",
    "nimi",
  ],
  category: ["category", "type", "product_type", "group", "kategoria"],
  price: ["price", "price_eur", "price_€", "cost", "hinta"],
  summary: ["summary", "description", "short_description", "kuvaus"],
  details: [
    "details",
    "long_description",
    "features",
    "key_features",
    "specs",
    "specifications",
  ],
  audience: ["audience", "customer_type", "segment", "suitable_for"],
  duration: [
    "delivery_time",
    "delivery",
    "availability",
    "duration",
    "lead_time",
    "toimitusaika",
  ],
  tags: ["tags", "keywords", "best_for", "use_cases"],
} as const;

function normaliseHeader(header: string): string {
  return header
    .toLowerCase()
    .replace(/[^\p{L}\p{N}€]+/gu, "_")
    .replace(/^_+|_+$/g, "");
}

function titleCase(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function formatPrice(value: string, header: string): string {
  const v = value.trim();
  if (!v) return "Price not stated";
  // A bare number in a column named after euros: show it as money.
  if (/^[\d\s.,]+$/.test(v) && /eur|€/.test(header)) return `€${v}`;
  return v;
}

/** Catalogue entries (services, products, requests...) from a CSV. The columns are found by name; the rest are added to the details. */
export function servicesFromCsv(
  text: string,
  fileName: string,
): { services: Service[]; warnings: string[] } {
  const rows = parseCsv(text);
  const warnings: string[] = [];
  if (rows.length < 2) {
    return {
      services: [],
      warnings: ["The CSV needs a header row and at least one row of entries."],
    };
  }
  const headers = rows[0].map(normaliseHeader);
  const find = (aliases: readonly string[]) =>
    headers.findIndex((h) => aliases.includes(h));
  const col = {
    name: find(COLUMNS.name),
    category: find(COLUMNS.category),
    price: find(COLUMNS.price),
    summary: find(COLUMNS.summary),
    details: find(COLUMNS.details),
    audience: find(COLUMNS.audience),
    duration: find(COLUMNS.duration),
    tags: find(COLUMNS.tags),
  };
  if (col.name < 0) {
    return {
      services: [],
      warnings: [
        `No name column found. Name one of the columns: ${COLUMNS.name.slice(0, 4).join(", ")}.`,
      ],
    };
  }
  if (col.price < 0)
    warnings.push("No price column found, so no prices are shown.");

  const mapped = new Set(Object.values(col).filter((i) => i >= 0));
  const services: Service[] = [];
  const seen = new Set<string>();
  for (const row of rows.slice(1)) {
    const cell = (i: number) => (i >= 0 ? (row[i] ?? "").trim() : "");
    const name = cell(col.name);
    if (!name) continue;
    let id = slug(name);
    for (let n = 2; seen.has(id); n++) id = `${slug(name)}-${n}`;
    seen.add(id);

    // Columns that are not recognised are kept as "Header: value" in the details.
    const extra = rows[0]
      .map((header, i) => ({ header, value: (row[i] ?? "").trim(), i }))
      .filter(({ i, value }) => !mapped.has(i) && value !== "")
      .map(({ header, value }) => `${header}: ${value}`);
    const details = [cell(col.details), ...extra].filter(Boolean).join(". ");
    const category = cell(col.category);
    const audiences = cell(col.audience)
      .split(/[;|/]/)
      .map((a) => slug(a, 30))
      .filter((a) => a !== "item");

    services.push({
      id,
      name: clip(name, 120),
      category: category ? slug(category, 40) : "general",
      audiences: audiences.length ? audiences : ["everyone"],
      summary: clip(cell(col.summary) || name, 300),
      details: clip(details || cell(col.summary) || name, LIMITS.articleChars),
      price: clip(formatPrice(cell(col.price), headers[col.price] ?? ""), 120),
      duration: clip(cell(col.duration) || "Not stated", 120),
      team: "support",
      tags: [
        ...cell(col.tags)
          .split(/[;|,]/)
          .map((t) => clip(t.trim().toLowerCase().replace(/\.+$/, ""), 40))
          .filter(Boolean),
        ...tagsFrom(`${name} ${category}`),
      ].slice(0, 12),
    });
  }
  if (services.length === 0) warnings.push(`No entries found in ${fileName}.`);
  return { services, warnings };
}

// ---------------------------------------------------------------------------
// Documents -> knowledge
// ---------------------------------------------------------------------------

/** Read one file's text. A .csv is the catalogue; anything else is FAQ text. */
export function loadDocument(name: string, text: string): LoadedDocument {
  if (/\.csv$/i.test(name)) {
    const { services, warnings } = servicesFromCsv(text, name);
    return { name, kind: "catalogue", articles: [], services, warnings };
  }
  const articles = articlesFromText(text, name);
  return {
    name,
    kind: "articles",
    articles,
    services: [],
    warnings:
      articles.length === 0 ? [`No readable text found in ${name}.`] : [],
  };
}

function cleanOrganisation(text: string): string {
  const clean = text
    .replace(/[\u0000-\u001f]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return clip(clean, LIMITS.organisationChars) || "Your organisation";
}

/** The knowledge of a helpdesk made from the user's documents. */
export function buildKnowledge(
  organisationName: string,
  documents: LoadedDocument[],
): Knowledge {
  const organisation = cleanOrganisation(organisationName);
  const services: Service[] = [];
  const articles: Article[] = [];
  const serviceIds = new Set<string>();
  const articleIds = new Set<string>();
  let chars = 0;

  for (const document of documents) {
    for (const s of document.services) {
      if (services.length >= LIMITS.services) break;
      const size = s.name.length + s.summary.length + s.details.length;
      if (chars + size > LIMITS.totalChars) break;
      let id = s.id;
      for (let n = 2; serviceIds.has(id); n++) id = `${s.id}-${n}`;
      serviceIds.add(id);
      services.push({ ...s, id });
      chars += size;
    }
    for (const a of document.articles) {
      if (articles.length >= LIMITS.articles) break;
      const size = a.title.length + a.body.length;
      if (chars + size > LIMITS.totalChars) break;
      let id = a.id;
      for (let n = 2; articleIds.has(id); n++) id = `${a.id}-${n}`;
      articleIds.add(id);
      articles.push({ ...a, id });
      chars += size;
    }
  }

  const categoryLabels: Record<string, string> = {};
  for (const s of services) {
    categoryLabels[s.category] ??= titleCase(s.category.replace(/-/g, " "));
  }
  const categories = Object.keys(categoryLabels);
  const audiences = [...new Set(services.flatMap((s) => s.audiences))];

  return {
    id: OWN_ID,
    organisation,
    helpdeskName: `${organisation} Helpdesk`,
    persona:
      "a helpdesk that answers questions from the organisation's own documents: its FAQ and guides, and a list of its services, products or requests",
    scope: "what the organisation's own documents cover",
    faqTopics: "the uploaded FAQ, guides and policies",
    serviceNoun:
      "catalogue entries (services, products or requests), with prices where the documents give them",
    handoffExample: "I would like to ask about ...",
    categories: (categories.length ? categories : ["general"]) as [
      string,
      ...string[],
    ],
    categoryLabels: categories.length ? categoryLabels : { general: "General" },
    audiences: (audiences.length ? audiences : ["everyone"]) as [
      string,
      ...string[],
    ],
    teams: {
      support: {
        name: "Support team",
        responseTime: "1 working day",
        handles:
          "questions the documents do not answer, and anything that needs a person",
      },
    },
    services,
    articles,
    userProvided: true,
  };
}

/** The helpdesk the chat plays for the user's own documents: no scripted demo and no suggested questions, since nothing is known beforehand about what the documents are for. */
export function ownExample(knowledge: Knowledge): HelpdeskExample {
  return {
    id: OWN_ID,
    title: knowledge.helpdeskName,
    summary: "",
    tags: [],
    knowledge,
    welcomeText:
      "Ask about anything in your documents. Answers come only from them, with the entries used shown, and a person can take over when needed.",
    starters: [],
  };
}

// ---------------------------------------------------------------------------
// The server's check of what the browser sends
// ---------------------------------------------------------------------------

const text = (max: number) => z.string().max(max);

const serviceSchema = z.object({
  id: text(80).min(1),
  name: text(120).min(1),
  category: text(40).min(1),
  audiences: z.array(text(30)).min(1).max(10),
  summary: text(300),
  details: text(LIMITS.articleChars),
  price: text(120),
  duration: text(120),
  team: z.literal("support"),
  tags: z.array(text(40)).max(12),
});

const articleSchema = z.object({
  id: text(120).min(1),
  title: text(120).min(1),
  body: text(LIMITS.articleChars).min(1),
  tags: z.array(text(40)).max(12),
});

const knowledgeSchema = z
  .object({
    id: z.literal(OWN_ID),
    organisation: text(LIMITS.organisationChars).min(1),
    helpdeskName: text(LIMITS.organisationChars + 20).min(1),
    categories: z.array(text(40)).min(1).max(40),
    categoryLabels: z.record(z.string(), text(60)),
    audiences: z.array(text(30)).min(1).max(20),
    services: z.array(serviceSchema).max(LIMITS.services),
    articles: z.array(articleSchema).max(LIMITS.articles),
  })
  .refine((k) => k.services.length + k.articles.length > 0, {
    message: "empty",
  })
  .refine(
    (k) =>
      k.services.every(
        (s) =>
          k.categories.includes(s.category) &&
          s.audiences.every((a) => k.audiences.includes(a)),
      ),
    { message: "inconsistent" },
  );

/**
 * The knowledge a request carries, checked. Only the user's content is taken
 * from it (documents, names); everything that steers the assistant (what it
 * is, what it stays on, the team) is set here, so a request cannot rewrite the
 * instructions. Returns null when it is not valid.
 */
export function parseOwnKnowledge(input: unknown): Knowledge | null {
  const parsed = knowledgeSchema.safeParse(input);
  if (!parsed.success) return null;
  const k = parsed.data;
  const chars = [
    ...k.services.map(
      (s) => s.name.length + s.summary.length + s.details.length,
    ),
    ...k.articles.map((a) => a.title.length + a.body.length),
  ].reduce((a, b) => a + b, 0);
  if (chars > LIMITS.totalChars) return null;

  const rebuilt = buildKnowledge(k.organisation, [
    {
      name: "request",
      kind: "catalogue",
      articles: [],
      services: k.services,
      warnings: [],
    },
    {
      name: "request",
      kind: "articles",
      articles: k.articles,
      services: [],
      warnings: [],
    },
  ]);
  // Keep the labels the user's categories had, where they are valid.
  for (const category of rebuilt.categories) {
    if (k.categoryLabels[category]) {
      rebuilt.categoryLabels[category] = k.categoryLabels[category];
    }
  }
  return rebuilt;
}
