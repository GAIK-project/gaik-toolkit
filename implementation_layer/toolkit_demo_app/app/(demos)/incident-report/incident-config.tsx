import type { ExtractionConfig } from "@/components/demo/extraction/config";
import type { GuideStep } from "@/components/demo/section-guide";
import {
  FileCode2,
  FileSearch,
  FileText,
  FileUp,
  ListChecks,
  Play,
  SearchCheck,
  Sparkles,
} from "lucide-react";
import { IncidentCard } from "./incident-card";
import {
  DEFAULT_FIELD_IDS,
  EXAMPLE_SCHEMA_KEY,
  INCIDENT_FIELDS,
  MAX_OWN_FIELDS,
  MAX_PROMPT_CHARS,
  REPORT_LANGUAGES,
  composeIncidentPrompt,
  examplePrompt,
  withLanguage,
} from "./incident-data";
import { INCIDENT_EXAMPLES, SLIP_TEXT } from "./incident-examples";

const EXAMPLE_STEPS: GuideStep[] = [
  {
    icon: FileSearch,
    title: "Pick an example",
    text: "Casual reports, a shift log with two incidents, Finnish reports or a spoken one.",
  },
  {
    icon: FileText,
    title: "Read or play it",
    text: "See the report as it was written or recorded, and the fields that will be read from it.",
  },
  {
    icon: Play,
    title: "Process the example",
    text: "The steps show the progress. Audio is transcribed first.",
  },
  {
    icon: ListChecks,
    title: "Explore the result",
    text: "Click any value to see where it comes from in the source. Edit the text and extract again, or open the PDF report.",
  },
];

const CREATE_STEPS: GuideStep[] = [
  {
    icon: FileUp,
    title: "Add a report",
    text: "Type or paste text, add an audio recording, or a photo or scan of a paper form. Or press Use example.",
  },
  {
    icon: ListChecks,
    title: "Decide what to extract",
    text: "Tick fields, add your own, edit the prompt, or write it yourself. Choose the language of the extracted values.",
  },
  {
    icon: FileCode2,
    title: "Generate the schema",
    text: "Press Generate schema, then check the fields it made. Generate it again whenever you change the fields, the prompt or the language.",
  },
  {
    icon: Sparkles,
    title: "Extract",
    text: "Press Extract. The report is read with the schema. Audio is transcribed first.",
  },
  {
    icon: SearchCheck,
    title: "Review and refine",
    text: "Click a value to see where it comes from. Fix the text and extract again, or change the fields and re-run.",
  },
];

export const INCIDENT_CONFIG: ExtractionConfig = {
  recordNoun: "incident",
  recordsNoun: "incidents",
  pdfTitle: "Incident Report",
  demoName: "incident-report",
  exampleSchemaKey: EXAMPLE_SCHEMA_KEY,
  fields: INCIDENT_FIELDS,
  defaultFieldIds: DEFAULT_FIELD_IDS,
  exampleFieldLabels: INCIDENT_FIELDS.map((field) => field.label),
  examplePrompt: examplePrompt(),
  examples: INCIDENT_EXAMPLES,
  languages: REPORT_LANGUAGES,
  maxOwnFields: MAX_OWN_FIELDS,
  maxPromptChars: MAX_PROMPT_CHARS,
  composePrompt: composeIncidentPrompt,
  withLanguage,
  sampleText: SLIP_TEXT,
  allowPhoto: true,
  sampleAudioUrl: "/sample.m4a",
  enhancedDefault: false,
  enhancedHint: "Clean up grammar and filler words (for Finnish speech only)",
  textPlaceholder:
    "Describe the incident: when, where, who was involved, injuries, and what was done...",
  ownPromptPlaceholder: `Extract the following from the incident report:
- Incident type (slip, near miss, equipment failure, ...)
- Severity (low, medium, high or critical)
- Corrective actions that are recommended`,
  exampleGuide: {
    steps: EXAMPLE_STEPS,
    notes: [
      "The examples use a saved schema, so they run quickly. To choose your own fields or language, open Test on your own data or examples.",
    ],
    intro:
      "An incident arrives as a short report, a log or a recording. The model reads out the structured details: when, where, who, what and what was done. Pick a report, see what is read from it, then process it.",
  },
  createGuide: {
    steps: CREATE_STEPS,
    notes: [
      "Field names stay in English; the language setting changes the extracted values only.",
      "Reports with several incidents give one entry for each. Nothing you add is kept as a use case: the schema lives for this session.",
    ],
    intro:
      "Extract your own data from incident reports, logs, recordings or photos of paper forms. The schema is generated for this session and is not saved.",
  },
  exampleFieldsHint: "Want other fields? Test on your own data.",
  createLinkText:
    "Want other fields or your own reports? Test on your own data",
  RecordCard: IncidentCard,
};
