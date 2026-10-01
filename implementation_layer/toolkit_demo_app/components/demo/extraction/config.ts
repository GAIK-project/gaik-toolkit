// What one demo supplies to the shared "example" and "test on your own data" sections.

import type { GuideStep } from "@/components/demo/section-guide";
import type { ReactNode } from "react";

export interface ExtractionField {
  id: string;
  label: string;
  /** Sent to the model: what the field means. */
  meaning: string;
  group: "core" | "extra";
}

export interface ExtractionExample {
  id: string;
  title: string;
  summary: string;
  kind: "text" | "audio";
  language: string;
  /** The report itself (text examples) or the audio file to transcribe. */
  text?: string;
  audioUrl?: string;
}

export interface OwnField {
  name: string;
  meaning: string;
}

/** What a result card is given for one extracted record. */
export interface RecordCardProps {
  report: Record<string, unknown>;
  index: number;
  total: number;
  /** The value that is picked, to mark it. */
  active: string | null;
  onPick: (text: string) => void;
}

export interface ExtractionConfig {
  /** "incident" -> "1 incident extracted". */
  recordNoun: string;
  recordsNoun: string;
  pdfTitle: string;
  /** For analytics. */
  demoName: string;
  /** The saved schema of the examples. */
  exampleSchemaKey: string;
  fields: ExtractionField[];
  defaultFieldIds: string[];
  /** The fields of the saved example schema, as the labels shown on the example. */
  exampleFieldLabels: string[];
  examplePrompt: string;
  examples: ExtractionExample[];
  languages: readonly string[];
  maxOwnFields: number;
  maxPromptChars: number;
  composePrompt: (selected: string[], own: OwnField[]) => string;
  withLanguage: (prompt: string, language: string) => string;
  /** The text of "Use example" in the section for your own data. */
  sampleText: string;
  allowPhoto: boolean;
  /** The recording that "Use example" adds in the section for your own data. */
  sampleAudioUrl: string;
  enhancedDefault: boolean;
  enhancedHint: string;
  textPlaceholder: string;
  ownPromptPlaceholder: string;
  exampleGuide: { steps: GuideStep[]; notes: string[]; intro: string };
  createGuide: { steps: GuideStep[]; notes: string[]; intro: string };
  /** Shown beside "Extracted by AI" on the example. */
  exampleFieldsHint: string;
  /** Link text on the example that opens the other section. */
  createLinkText: string;
  RecordCard: (props: RecordCardProps) => ReactNode;
}
