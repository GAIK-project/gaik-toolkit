// What the Knowledge Curator demo works with: ready-made source sets with the topics to
// collect, and how a set of facts is searched, filtered, counted and found in its source.

import type {
  FactUnit,
  SectionInput,
  SectionKnowledge,
} from "@/lib/knowledge-curator/workspace";

export interface CuratorExample {
  id: string;
  title: string;
  summary: string;
  tags: string[];
  /** The normalized sources, a JSON file of path to text in public/. */
  url: string;
  sections: SectionInput[];
  instructions: string;
}

export const EXAMPLES: CuratorExample[] = [
  {
    id: "site",
    title: "A site meeting package",
    summary:
      "Meeting minutes, a visit note and a maintenance log, as the Source Normalizer makes them. Some items you ask for no source covers, and the report lists them as missing.",
    tags: ["3 sources", "3 topics", "missing items"],
    url: "/knowledge-curator-examples/site-package.json",
    sections: [
      {
        id: "roof",
        title: "Roof",
        instructions:
          "The condition of the roof, the damage found, and what is being done about it.",
        required_items: [
          "number of cracked tiles",
          "latest roof repair",
          "condition of the gutters",
        ],
      },
      {
        id: "facade",
        title: "Facade and moisture",
        instructions: "Water damage and the state of the east wall.",
        required_items: ["extent of the water damage"],
      },
      {
        id: "schedule",
        title: "Schedule and actions",
        instructions:
          "How the work stands against the schedule, and who must do what by when.",
        required_items: ["date of the next meeting"],
      },
    ],
    instructions:
      "The meeting minutes and the site notes are primary sources. The maintenance log is secondary. When sources disagree, prefer the primary source. Write the summaries in English.",
  },
  {
    id: "sale",
    title: "A pre-sale inspection where sources disagree",
    summary:
      "An inspector's notes and readings against the seller's disclosure. They disagree about the roof and the bathroom, and the instructions say which to trust.",
    tags: ["3 sources", "3 topics", "conflicts"],
    url: "/knowledge-curator-examples/sale-inspection.json",
    sections: [
      {
        id: "roof",
        title: "Roof",
        instructions:
          "The age and condition of the roof underlay, and any leaks.",
        required_items: ["age of the roof underlay"],
      },
      {
        id: "bathroom",
        title: "Bathroom",
        instructions:
          "Moisture, joints and the renovation history of the bathroom.",
        required_items: [
          "latest moisture reading",
          "year of the last renovation",
        ],
      },
      {
        id: "plumbing",
        title: "Plumbing",
        instructions: "The condition and the renovation of the pipes.",
        required_items: [
          "condition of the supply pipes",
          "year of the supply pipe renovation",
        ],
      },
    ],
    instructions:
      "The inspector's notes and the moisture readings are primary sources. The seller's disclosure is secondary. When they disagree, prefer the primary source, and keep the seller's claim as a resolved conflict. Write the summaries in English.",
  },
];

// ---------------------------------------------------------------------------
// Finding a quote in its source
// ---------------------------------------------------------------------------

/** The text with ligatures and compatibility forms folded, whitespace runs made one
 * space, and no case, with where each kept character came from. */
function fold(text: string): { text: string; from: number[] } {
  let out = "";
  const from: number[] = [];
  let previousSpace = true;
  for (let index = 0; index < text.length; index += 1) {
    // A character may fold to several (a ligature to two letters).
    const folded = text[index].normalize("NFKC").toLowerCase();
    for (const char of folded) {
      if (/\s/.test(char)) {
        if (previousSpace) continue;
        out += " ";
        from.push(index);
        previousSpace = true;
      } else {
        out += char;
        from.push(index);
        previousSpace = false;
      }
    }
  }
  return { text: out, from };
}

/** Where a quote is in a source: the same words, whatever the spacing, ligatures or case. */
export function findQuote(
  source: string,
  quote: string,
): { start: number; end: number } | null {
  const needle = fold(quote).text.trim();
  if (needle === "") return null;
  const haystack = fold(source);
  const at = haystack.text.indexOf(needle);
  if (at < 0) return null;
  const start = haystack.from[at];
  const end = haystack.from[at + needle.length - 1] + 1;
  return { start, end };
}

// ---------------------------------------------------------------------------
// Reading the facts
// ---------------------------------------------------------------------------

export interface Fact extends FactUnit {
  /** The topic file the fact is in. */
  sectionId: string;
}

export function allFacts(knowledge: SectionKnowledge[]): Fact[] {
  return knowledge.flatMap((section) =>
    section.units.map((unit) => ({ ...unit, sectionId: section.section_id })),
  );
}

export interface FactFilter {
  query: string;
  confidence: string | null;
  file: string | null;
  sourceClass: string | null;
}

export const NO_FILTER: FactFilter = {
  query: "",
  confidence: null,
  file: null,
  sourceClass: null,
};

export function matchesFilter(fact: Fact, filter: FactFilter): boolean {
  if (filter.confidence && fact.confidence !== filter.confidence) return false;
  if (filter.file && fact.source.file !== filter.file) return false;
  if (filter.sourceClass && fact.source_class !== filter.sourceClass)
    return false;
  const needle = filter.query.trim().toLowerCase();
  if (needle === "") return true;
  return [fact.topic, fact.summary, fact.quote, fact.time_qualifier ?? ""].some(
    (text) => text.toLowerCase().includes(needle),
  );
}

export interface Totals {
  topics: number;
  facts: number;
  missing: number;
  conflicts: number;
  unresolved: number;
}

export function totalsOf(knowledge: SectionKnowledge[]): Totals {
  const conflicts = knowledge.flatMap((section) => section.conflicts);
  return {
    topics: knowledge.length,
    facts: knowledge.reduce((sum, section) => sum + section.units.length, 0),
    missing: knowledge.reduce(
      (sum, section) => sum + section.missing.length,
      0,
    ),
    conflicts: conflicts.length,
    unresolved: conflicts.filter((c) => c.status.toLowerCase() === "unresolved")
      .length,
  };
}

/** The distinct values of a field of the facts, with how many facts have each. */
export function countBy(
  facts: Fact[],
  pick: (fact: Fact) => string | null,
): [string, number][] {
  const counts = new Map<string, number>();
  for (const fact of facts) {
    const key = pick(fact);
    if (key) counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()].sort(
    (a, b) => b[1] - a[1] || a[0].localeCompare(b[0]),
  );
}
