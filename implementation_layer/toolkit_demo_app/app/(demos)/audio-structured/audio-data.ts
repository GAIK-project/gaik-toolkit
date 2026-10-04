// What the Audio → Structured Data demo works with: ready-made recordings with the task that
// suits each, how the options become a request, and how the answer is read.

import {
  reusableSchemaId,
  savedSchemaKey,
  type MadeSchema,
} from "@/lib/schema-reuse";
import type { Language } from "../transcriber/transcriber-data";

export interface AudioOptions {
  language: Language;
  /** Tell the speakers apart (the HH server only). */
  diarization: boolean;
  /** How many people speak, when it is known. Empty lets the server decide. */
  speakers: string;
  /** Names, terms and the topic, sent to the transcriber as a hint. */
  context: string;
  /** A second pass corrects the text before the extraction (Finnish). */
  fixErrors: boolean;
  generatePdf: boolean;
}

export const DEFAULT_OPTIONS: AudioOptions = {
  language: "auto",
  diarization: false,
  speakers: "",
  context: "",
  fixErrors: false,
  generatePdf: false,
};

export interface AudioExample {
  id: string;
  title: string;
  /** The shape of the result, for the card. */
  shape: string;
  summary: string;
  tags: string[];
  /** The recording, a file in public/. */
  url: string;
  fileName: string;
  task: string;
  options: Partial<AudioOptions>;
  /**
   * The saved schema of this task (a file in api/schemas/). Only the task as written
   * here may use it: once the text is edited, a new schema is made.
   */
  schemaKey?: string;
}

export const EXAMPLES: AudioExample[] = [
  {
    id: "consultation",
    title: "A medical consultation",
    shape: "one record, ten fields",
    summary:
      "A doctor dictates what she found: symptoms, vital signs, diagnosis and treatment, written into a patient record.",
    tags: ["English", "93 s", "vital signs"],
    url: "/sample.mp3",
    fileName: "sample.mp3",
    schemaKey: "audio_structured_medical_default",
    task: `Extract the following from the audio:
- Date
- Patient's date of birth
- Symptoms (in few keywords)
- Medical history (in few keywords)
- Examination description (in few keywords)
- Body temperature / Heart Rate / Oxygen saturation
- Procedure performed (in few keywords)
- Diagnosis (in few keywords)
- Prescription (in few keywords)
- Follow-up (in few keywords)`,
    options: { language: "en" },
  },
  {
    id: "meeting",
    schemaKey: "audio_structured_meeting_example",
    title: "A site meeting",
    shape: "header + a list of actions",
    summary:
      "Two people agree who does what. The result has the meeting details and a list with one row per action, with who is responsible.",
    tags: ["Finnish", "46 s", "2 speakers", "list"],
    url: "/transcriber-examples/site-meeting-fi.mp3",
    fileName: "site-meeting-fi.mp3",
    task: `Extract the details of a site meeting. Return the meeting topic, a short summary in English, and whether the schedule is on time (on_time or delayed) with the delay in weeks as a number (null if on time).
Also return a list of the action items. For each, extract the task, the person responsible, the deadline (as said in the recording) and whether it is a booking, a delivery or a confirmation (booking, delivery, confirmation). The deadline can be null.
Write the values in English.`,
    options: { language: "fi", diarization: true, speakers: "2" },
  },
  {
    id: "diary",
    schemaKey: "audio_structured_diary_example",
    title: "A site diary dictation",
    shape: "one record, with lists",
    summary:
      "A foreman dictates the day on a demolition site, in Finnish. The values are written in English, and numbers are numbers.",
    tags: ["Finnish", "47 s", "translated", "numbers"],
    url: "/sample2.m4a",
    fileName: "sample2.m4a",
    task: `Extract the entries of a construction site diary: the site address, the date as said (as text: it may have no month or year), the number of subcontractors and the number of own machine operators on site, the work in progress, the progress of the interior demolition on the upper and the lower floor (percent done, as a number), the utilities cut off, and the calls made. Write the values in English.`,
    options: { language: "fi" },
  },
  {
    id: "note",
    schemaKey: "audio_structured_note_example",
    title: "A safety observation",
    shape: "one record, a yes/no",
    summary:
      "A 14-second voice note about poor ventilation in a workshop. The quickest way to see the whole pipeline.",
    tags: ["Finnish", "14 s", "quick"],
    url: "/Sample11.m4a",
    fileName: "Sample11.m4a",
    task: `Extract a safety observation: who reported it (name), the date, the place, the problem, how it affects the workers, and whether it needs a repair (yes or no). Write the values in English.`,
    options: { language: "fi" },
  },
];

// ---------------------------------------------------------------------------
// The request
// ---------------------------------------------------------------------------

/** The schema key to send: the saved one only while the task is exactly the example's. */
export function schemaKeyFor(
  example: AudioExample | null,
  task: string,
): string {
  return savedSchemaKey(example, task);
}

export { reusableSchemaId, type MadeSchema };

/** The form fields of a request, as pairs, so that they can be checked without a browser. */
export function formFields(
  options: AudioOptions,
  task: string,
  schemaKey: string,
  schemaId: string | null = null,
): [string, string][] {
  const fields: [string, string][] = [
    ["user_requirements", task],
    ["generate_pdf", String(options.generatePdf)],
    ["pdf_title", "Audio Structured Data"],
    ["compress_audio", "true"],
    ["language", options.language],
    ["diarization", String(options.diarization)],
    ["fix_transcription_errors", String(options.fixErrors)],
    // The saved schema is used as it is; a task that was edited gets a new one.
    ["schema_key", schemaKey],
    ["regenerate_schema", "false"],
  ];
  // The schema made in an earlier run of this very task is used again, not made again.
  if (schemaId && !schemaKey) fields.push(["schema_id", schemaId]);
  const speakers = Number.parseInt(options.speakers, 10);
  if (options.diarization && Number.isFinite(speakers) && speakers > 0) {
    fields.push(["min_speakers", String(speakers)]);
    fields.push(["max_speakers", String(speakers)]);
  }
  if (options.context.trim() !== "")
    fields.push(["custom_context", options.context.trim()]);
  return fields;
}

// ---------------------------------------------------------------------------
// The answer
// ---------------------------------------------------------------------------

export interface Timings {
  transcription_s: number;
  schema_s: number;
  extraction_s: number;
}

/** What took how long, for the line under the result. */
export function timingText(timings: Timings | null | undefined): string {
  if (!timings) return "";
  return [
    `transcription ${timings.transcription_s.toFixed(1)} s`,
    `schema ${timings.schema_s.toFixed(1)} s`,
    `extraction ${timings.extraction_s.toFixed(1)} s`,
  ].join(" · ");
}

/** The transcript the extraction read: the corrected one when errors were fixed. */
export function transcriptRead(result: {
  enhanced_transcript: string | null;
  raw_transcript: string | null;
}): string {
  return (result.enhanced_transcript || result.raw_transcript || "").trim();
}
