// The fields a user can choose in the Incident Reporting demo, and how the choices
// become the extraction prompt.

export type IncidentField = {
  id: string;
  label: string;
  /** Sent to the model: what the field means. */
  meaning: string;
  group: "core" | "extra";
};

export const INCIDENT_FIELDS: IncidentField[] = [
  { id: "date", label: "Date", meaning: "Incident date", group: "core" },
  { id: "time", label: "Time", meaning: "Incident time", group: "core" },
  {
    id: "location",
    label: "Location",
    meaning: "Where the incident happened",
    group: "core",
  },
  {
    id: "description",
    label: "Description",
    meaning: "Brief description of what happened",
    group: "core",
  },
  {
    id: "people",
    label: "People involved",
    meaning: "Names, with roles if mentioned",
    group: "core",
  },
  {
    id: "injuries",
    label: "Injuries",
    meaning: "Injuries reported, if any",
    group: "core",
  },
  {
    id: "damages",
    label: "Damages",
    meaning: "Property or equipment damage, if any",
    group: "core",
  },
  {
    id: "actions",
    label: "Immediate actions",
    meaning: "Immediate actions taken",
    group: "core",
  },
  {
    id: "witnesses",
    label: "Witnesses",
    meaning: "Witness names, if any",
    group: "core",
  },
  {
    id: "severity",
    label: "Severity",
    meaning: "Severity: low, medium, high or critical, judged from the report",
    group: "extra",
  },
  {
    id: "type",
    label: "Incident type",
    meaning:
      "Type, such as slip or fall, near miss, equipment failure, vehicle, fire or spill",
    group: "extra",
  },
  {
    id: "root_cause",
    label: "Root cause",
    meaning: "The likely cause of the incident",
    group: "extra",
  },
  {
    id: "corrective",
    label: "Corrective actions",
    meaning: "Corrective or preventive actions, stated or recommended",
    group: "extra",
  },
  {
    id: "reported_by",
    label: "Reported by",
    meaning: "Who wrote or reported the incident",
    group: "extra",
  },
  {
    id: "equipment",
    label: "Equipment involved",
    meaning: "Machines, vehicles or tools involved",
    group: "extra",
  },
];

export const DEFAULT_FIELD_IDS = INCIDENT_FIELDS.filter(
  (field) => field.group === "core",
).map((field) => field.id);

export const MAX_OWN_FIELDS = 10;
export const MAX_PROMPT_CHARS = 4000;

export type OwnField = { name: string; meaning: string };

/** "Same as the report" leaves the language alone. */
export const REPORT_LANGUAGES = [
  "Same as the report",
  "English",
  "Finnish",
  "Swedish",
] as const;

/** The examples extract every field; their schema is saved under this key. */
export const EXAMPLE_SCHEMA_KEY = "incident_report_example";

export function composeIncidentPrompt(
  selected: string[],
  own: OwnField[],
): string {
  const lines = [
    ...INCIDENT_FIELDS.filter((field) => selected.includes(field.id)).map(
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
    "The text may describe one incident or several. Return a list called incidents with one entry for each incident. Each entry has these fields, all optional (leave out what the text does not mention):",
    ...lines,
  ].join("\n");
}

/** Adds the output-language instruction, unless the language is left as in the report. */
export function withLanguage(prompt: string, language: string): string {
  if (!language || language === REPORT_LANGUAGES[0]) return prompt;
  return `${prompt.trimEnd()}\nWrite all extracted values in ${language}.`;
}

/** The prompt of the examples: all fields, one list entry for each incident. */
export function examplePrompt(): string {
  return composeIncidentPrompt(
    INCIDENT_FIELDS.map((field) => field.id),
    [],
  );
}
