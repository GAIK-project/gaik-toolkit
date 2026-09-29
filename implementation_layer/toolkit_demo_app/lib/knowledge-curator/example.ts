// A small synthetic example (no real customer data): two normalized sources and two
// sections, so the demo can be tried without uploading anything.
import { MANIFEST_PATH } from "@/lib/source-normalizer/workspace";
import type { SectionInput } from "./workspace";

const NOTES = `Site visit, 14 March 2026, technical room.
The supply-air unit vibrates and the housing is rusty.
The maintenance sticker on the unit is dated 2019.`;

const REPORT = `[Page 1]
Renovation report, 1998.
[Page 3]
Mechanical ventilation installed during the 1998 renovation. Design life 25 years.
The roof underlay was not inspected during the renovation.`;

export const EXAMPLE_NORMALIZED: Record<string, string> = {
  "normalized/01_site_notes.md": NOTES,
  "normalized/02_renovation_report_1998.md": REPORT,
  [MANIFEST_PATH]: JSON.stringify(
    [
      {
        id: "01_site_notes",
        file: "site_notes.txt",
        source_class: "primary",
        source_type: "text",
        tool: "text",
      },
      {
        id: "02_renovation_report_1998",
        file: "renovation_report_1998.pdf",
        source_class: "secondary",
        source_type: "pdf",
        tool: "PyMuPDFParser",
      },
    ],
    null,
    2,
  ),
};

export const EXAMPLE_SECTIONS: SectionInput[] = [
  {
    id: "ventilation",
    title: "Ventilation",
    instructions: "Condition, age and maintenance of the ventilation system.",
    required_items: ["ventilation system and its age", "latest filter change"],
  },
  {
    id: "roof",
    title: "Roof",
    instructions: "Condition of the roof and its underlay.",
    required_items: [],
  },
];

export const EXAMPLE_INSTRUCTIONS =
  "Site notes are primary sources. Documents from the customer are secondary. When they disagree, prefer the primary source. Write the summaries in English.";
