// The fields a user can choose in the Construction Diary demo, and how the choices
// become the extraction prompt.

import type {
  ExtractionField,
  OwnField,
} from "@/components/demo/extraction/config";

export const DIARY_FIELDS: ExtractionField[] = [
  {
    id: "project",
    label: "Project",
    meaning: "Project or site name",
    group: "core",
  },
  {
    id: "author",
    label: "Author",
    meaning: "Who wrote the diary, with their role",
    group: "core",
  },
  {
    id: "date",
    label: "Date",
    meaning: "Date of the diary day",
    group: "core",
  },
  {
    id: "week",
    label: "Week number",
    meaning: "Work week number, if mentioned",
    group: "core",
  },
  {
    id: "weather",
    label: "Weather",
    meaning: "Weather conditions: temperature, wind, rain or snow",
    group: "core",
  },
  {
    id: "personnel",
    label: "Personnel",
    meaning: "People on site: supervisors, workers, subcontractors, total",
    group: "core",
  },
  {
    id: "work",
    label: "Work done",
    meaning: "The day's work tasks, one entry for each",
    group: "core",
  },
  {
    id: "events",
    label: "Events",
    meaning: "Notable events of the day",
    group: "core",
  },
  {
    id: "started",
    label: "Phases started",
    meaning: "Work phases that were started",
    group: "core",
  },
  {
    id: "ongoing",
    label: "Phases ongoing",
    meaning: "Work phases that are in progress",
    group: "core",
  },
  {
    id: "completed",
    label: "Phases completed",
    meaning: "Work phases that were completed",
    group: "core",
  },
  {
    id: "interrupted",
    label: "Phases interrupted",
    meaning: "Work phases that were interrupted or paused",
    group: "core",
  },
  {
    id: "observations",
    label: "Supervisor observations",
    meaning: "The supervisor's observations and remarks",
    group: "core",
  },
  {
    id: "deviations",
    label: "Deviations",
    meaning: "Deviations from the plan or the schedule",
    group: "core",
  },
  {
    id: "inspections",
    label: "Inspections",
    meaning: "Inspections, surveys or visits made",
    group: "core",
  },
  {
    id: "safety",
    label: "Safety",
    meaning: "Safety observations, near misses or accidents",
    group: "extra",
  },
  {
    id: "equipment",
    label: "Equipment",
    meaning: "Machines and equipment used on site",
    group: "extra",
  },
  {
    id: "deliveries",
    label: "Deliveries",
    meaning: "Material deliveries received",
    group: "extra",
  },
  {
    id: "delays",
    label: "Delays",
    meaning: "Delays and what caused them",
    group: "extra",
  },
  {
    id: "next_day",
    label: "Plans for the next day",
    meaning: "What is planned for the next working day",
    group: "extra",
  },
  {
    id: "attachments",
    label: "Attachments",
    meaning: "Photos or documents attached to the diary",
    group: "extra",
  },
];

export const DEFAULT_FIELD_IDS = DIARY_FIELDS.filter(
  (field) => field.group === "core",
).map((field) => field.id);

export const MAX_OWN_FIELDS = 10;
export const MAX_PROMPT_CHARS = 4000;

/** "Same as the diary" leaves the language alone. */
export const DIARY_LANGUAGES = [
  "Same as the diary",
  "English",
  "Finnish",
  "Swedish",
] as const;

/** The examples extract every field; their schema is saved under this key. */
export const EXAMPLE_SCHEMA_KEY = "construction_diary_example";

export function composeDiaryPrompt(
  selected: string[],
  own: OwnField[],
): string {
  const lines = [
    ...DIARY_FIELDS.filter((field) => selected.includes(field.id)).map(
      (field) => `- ${field.label} (${field.meaning})`,
    ),
    ...own
      .filter((field) => field.name.trim())
      .map((field) =>
        field.meaning.trim()
          ? `- ${field.name.trim()} (${field.meaning.trim()})`
          : `- ${field.name.trim()}`,
      ),
  ];
  return [
    "The text may cover one working day or several. Return a list called entries with one entry for each day. Each entry has these fields, all optional (leave out what the text does not mention):",
    ...lines,
  ].join("\n");
}

/** Adds the output-language instruction, unless the language is left as in the diary. */
export function withLanguage(prompt: string, language: string): string {
  if (!language || language === DIARY_LANGUAGES[0]) return prompt;
  return `${prompt.trimEnd()}\nWrite all extracted values in ${language}.`;
}

/** The prompt of the examples: all fields, one list entry for each day. */
export function examplePrompt(): string {
  return composeDiaryPrompt(
    DIARY_FIELDS.map((field) => field.id),
    [],
  );
}
