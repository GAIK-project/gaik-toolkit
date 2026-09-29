// A small synthetic example (no real customer data). Its sections match the knowledge of the
// Knowledge Curator's own example (ventilation and roof), so the two demos fit together:
// load the example there, curate, send the knowledge here, then load this example.
import type { SectionInput } from "./workspace";

export const EXAMPLE_TITLE = "Site report, Example House";
export const EXAMPLE_LANGUAGE = "English";
export const EXAMPLE_INSTRUCTIONS =
  "Use only the facts of the knowledge. Cite the source file of each fact. Use the sample report for structure and style only; never take facts from it.";

// The summary comes first in the report but is written last: it depends on the two others.
export const EXAMPLE_SECTIONS: SectionInput[] = [
  {
    id: "summary",
    title: "Summary",
    instructions: "Two or three sentences with the main findings and what needs attention.",
    required_items: [],
    depends_on: ["ventilation", "roof"],
  },
  {
    id: "ventilation",
    title: "Ventilation",
    instructions: "Condition, age and maintenance of the ventilation system.",
    required_items: ["ventilation system and its age", "latest filter change"],
    depends_on: [],
  },
  {
    id: "roof",
    title: "Roof",
    instructions: "Condition of the roof and its underlay.",
    required_items: [],
    depends_on: [],
  },
];

export const EXAMPLE_SAMPLE_NAME = "sample_report.md";

// About a different house on purpose: the report copies its shape, never its content.
export const EXAMPLE_SAMPLE = `# Site report, Sample Cottage

## Summary

The heating system is old but works. The floor slab needs a closer inspection next year.

## Heating

The system is described first, in one short paragraph.

- Condition: one line per observation.
- Age and service history: one line each.

## Floor slab

A short paragraph on the slab, followed by a bulleted list of the open questions.
`;
