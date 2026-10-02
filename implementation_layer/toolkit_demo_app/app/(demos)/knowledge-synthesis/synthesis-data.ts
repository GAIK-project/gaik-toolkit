// What the Knowledge Synthesis demo works with: ready-made knowledge with the report to
// write from it, and how a written report is counted and read.

import type { SectionInput } from "@/lib/knowledge-synthesis/workspace";

export interface SynthesisExample {
  id: string;
  title: string;
  summary: string;
  tags: string[];
  /** The curated knowledge: a JSON file of knowledge/<id>.json to text, in public/. */
  url: string;
  reportTitle: string;
  language: string;
  instructions: string;
  sections: SectionInput[];
  /** A sample report to copy the shape of, or null for none. */
  sample: { name: string; text: string } | null;
}

// About a different house on purpose: the report copies its shape, never its content.
const SAMPLE = `# Condition report, Sample Cottage

## Overall assessment

Two or three sentences with the main finding and what needs attention first.

## Heating

A short paragraph on the system, then one line for each observation:

- Condition: what was seen.
- Age and service history: when it was last serviced.

## Floor slab

A short paragraph on the slab, then a bulleted list of the open questions.
`;

export const EXAMPLES: SynthesisExample[] = [
  {
    id: "site",
    title: "A site report from the meeting package",
    summary:
      "The facts curated from the minutes, the visit note and the maintenance log become a four-part report. The summary is derived: it is written last, from the three sections before it.",
    tags: ["3 topics", "1 derived section", "no sample report"],
    url: "/knowledge-synthesis-examples/site-package.json",
    reportTitle: "Site report, Kometankuja 6",
    language: "English",
    instructions:
      "Use only the facts of the knowledge. Cite the source file of each fact in parentheses. Show an item no source covers as (missing: …). Keep the sections short.",
    sections: [
      {
        id: "summary",
        title: "Summary",
        instructions:
          "Two or three sentences with the main findings and what needs attention first.",
        required_items: [],
        depends_on: ["roof", "facade", "schedule"],
      },
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
        depends_on: [],
      },
      {
        id: "facade",
        title: "Facade and moisture",
        instructions: "Water damage and the state of the east wall.",
        required_items: ["extent of the water damage"],
        depends_on: [],
      },
      {
        id: "schedule",
        title: "Schedule and actions",
        instructions:
          "How the work stands against the schedule, and who must do what by when.",
        required_items: ["date of the next meeting"],
        depends_on: [],
      },
    ],
    sample: null,
  },
  {
    id: "sale",
    title: "A pre-sale condition report with a sample",
    summary:
      "The inspector's facts against the seller's disclosure, written up in the shape of a sample report. The report must say where the sources disagree.",
    tags: ["3 topics", "conflicts", "sample report"],
    url: "/knowledge-synthesis-examples/sale-inspection.json",
    reportTitle: "Condition report, Satamakatu 8 B 24",
    language: "English",
    instructions:
      "Use only the facts of the knowledge. Cite the source file of each fact. When the sources disagree, state the primary source's finding and mention that the seller's disclosure says otherwise. Use the sample report for structure and style only; never take facts from it.",
    sections: [
      {
        id: "overall",
        title: "Overall assessment",
        instructions:
          "Two or three sentences with the main finding and what needs attention first.",
        required_items: [],
        depends_on: ["roof", "bathroom", "plumbing"],
      },
      {
        id: "roof",
        title: "Roof",
        instructions:
          "The age and condition of the roof underlay, and any leaks.",
        required_items: ["age of the roof underlay"],
        depends_on: [],
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
        depends_on: [],
      },
      {
        id: "plumbing",
        title: "Plumbing",
        instructions: "The condition and the renovation of the pipes.",
        required_items: [
          "condition of the supply pipes",
          "year of the supply pipe renovation",
        ],
        depends_on: [],
      },
    ],
    sample: { name: "sample_report.md", text: SAMPLE },
  },
];

// ---------------------------------------------------------------------------
// Reading a written report
// ---------------------------------------------------------------------------

export function wordCount(text: string): number {
  const trimmed = text.trim();
  return trimmed === "" ? 0 : trimmed.split(/\s+/).length;
}

/** How many times each source file is named in a text, for the files named at least once. */
export function citationCounts(
  text: string,
  files: string[],
): [string, number][] {
  const counts: [string, number][] = [];
  for (const file of files) {
    let count = 0;
    for (
      let at = text.indexOf(file);
      at >= 0;
      at = text.indexOf(file, at + file.length)
    )
      count += 1;
    if (count > 0) counts.push([file, count]);
  }
  return counts.sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

/** The items the writer marked as covered by no source. */
export function missingMarkers(text: string): string[] {
  return [...text.matchAll(/\(missing:\s*([^)]*)\)/gi)].map((match) =>
    match[1].trim(),
  );
}

export interface SectionFigures {
  id: string;
  words: number;
  citations: number;
  missing: number;
}

export function figuresOf(
  sections: { id: string; text: string }[],
  files: string[],
): SectionFigures[] {
  return sections.map((section) => ({
    id: section.id,
    words: wordCount(section.text),
    citations: citationCounts(section.text, files).reduce(
      (sum, [, count]) => sum + count,
      0,
    ),
    missing: missingMarkers(section.text).length,
  }));
}

/** The files that facts of the knowledge cite, from knowledge JSON texts. */
export function sourceFilesOf(knowledgeTexts: string[]): string[] {
  const files = new Set<string>();
  for (const text of knowledgeTexts) {
    try {
      const parsed = JSON.parse(text) as {
        units?: { source?: { file?: string } }[];
      };
      for (const unit of parsed.units ?? [])
        if (unit.source?.file) files.add(unit.source.file);
    } catch {
      // A file that is not JSON has no sources to name.
    }
  }
  return [...files].sort();
}
