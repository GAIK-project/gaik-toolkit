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
import { DiaryCard } from "./diary-card";
import {
  DEFAULT_FIELD_IDS,
  DIARY_FIELDS,
  DIARY_LANGUAGES,
  EXAMPLE_SCHEMA_KEY,
  MAX_OWN_FIELDS,
  MAX_PROMPT_CHARS,
  composeDiaryPrompt,
  examplePrompt,
  withLanguage,
} from "./diary-data";
import { DIARY_EXAMPLES, TYPED_TEXT } from "./diary-examples";

const EXAMPLE_STEPS: GuideStep[] = [
  {
    icon: FileSearch,
    title: "Pick an example",
    text: "Typed or dictated diaries in English and Finnish, three days in one text, or a spoken one.",
  },
  {
    icon: FileText,
    title: "Read or play it",
    text: "See the diary as it was written or recorded, and the fields that will be read from it.",
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
    title: "Add a diary",
    text: "Type or paste text, or add an audio recording. Or press Use example.",
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
    text: "Press Extract. The diary is read with the schema. Audio is transcribed first.",
  },
  {
    icon: SearchCheck,
    title: "Review and refine",
    text: "Click a value to see where it comes from. Fix the text and extract again, or change the fields and re-run.",
  },
];

export const DIARY_CONFIG: ExtractionConfig = {
  recordNoun: "diary entry",
  recordsNoun: "diary entries",
  pdfTitle: "Construction Diary",
  demoName: "diary",
  exampleSchemaKey: EXAMPLE_SCHEMA_KEY,
  fields: DIARY_FIELDS,
  defaultFieldIds: DEFAULT_FIELD_IDS,
  exampleFieldLabels: DIARY_FIELDS.map((field) => field.label),
  examplePrompt: examplePrompt(),
  examples: DIARY_EXAMPLES,
  languages: DIARY_LANGUAGES,
  maxOwnFields: MAX_OWN_FIELDS,
  maxPromptChars: MAX_PROMPT_CHARS,
  composePrompt: composeDiaryPrompt,
  withLanguage,
  sampleText: TYPED_TEXT,
  allowPhoto: false,
  sampleAudioUrl: "/diary-fi-dictation.mp3",
  enhancedDefault: true,
  enhancedHint: "Clean up grammar and filler words (for Finnish speech only)",
  textPlaceholder:
    "Write the day's diary: project, date, weather, people on site, work done, events and observations...",
  ownPromptPlaceholder: `Extract the following from the construction diary:
- Project and date
- Number of workers on site
- Work that was delayed and why`,
  exampleGuide: {
    steps: EXAMPLE_STEPS,
    notes: [
      "The examples use a saved schema, so they run quickly. To choose your own fields or language, open Test on your own data or examples.",
    ],
    intro:
      "A site supervisor writes or dictates the day's diary in plain words. The model reads out the structured entry: when, where, who was on site, what was done, what happened and what comes next. Pick a diary, see what is read from it, then process it.",
  },
  createGuide: {
    steps: CREATE_STEPS,
    notes: [
      "Field names stay in English; the language setting changes the extracted values only.",
      "A text that covers several days gives one entry for each day. Nothing you add is kept as a use case: the schema lives for this session.",
    ],
    intro:
      "Extract your own data from typed or dictated construction diaries. The schema is generated for this session and is not saved.",
  },
  exampleFieldsHint: "Want other fields? Test on your own data.",
  createLinkText:
    "Want other fields or your own diaries? Test on your own data",
  RecordCard: DiaryCard,
};
