// The dialect comparison on the Transcriber page: what five models wrote for six
// clips of Finnish dialect interviews, against the human transcript.
//
// dialect-samples.json is exported from GAIK-project/finnish-asr
// (results/benchmarks/skn_fi, the commit in its `source`): the clips come from
// the 10 SKN municipalities that no model was trained on, every model decoded
// them the same way, and a word counts as wrong as finnish-asr's scorer counts it
// (lower-cased, punctuation removed). The audio is in
// public/transcriber-examples/dialects/, cut from the dataset's test split.

import samples from "./dialect-samples.json";

export type ModelId =
  | "ft_whisper-large-v3-fi-parl"
  | "hf_whisper-large-finnish-v3"
  | "hf_whisper-large-v3"
  | "azure_gpt-4o-transcribe"
  | "google_chirp-3";

export type Maker = "gaik" | "huggingface" | "openai" | "google";

export interface DialectModel {
  id: ModelId;
  name: string;
  /** For the bars, where the full name does not fit. */
  short?: string;
  /** Where it runs, or what it is here. */
  note: string;
  maker: Maker;
  ours?: boolean;
}

export const DIALECT_MODELS: DialectModel[] = [
  {
    id: "ft_whisper-large-v3-fi-parl",
    name: "GAIK dialect model",
    note: "Whisper large-v3 fine-tuned for Finnish dialects",
    maker: "gaik",
    ours: true,
  },
  {
    id: "hf_whisper-large-finnish-v3",
    name: "Finnish-NLP whisper-large-finnish-v3",
    short: "Finnish-NLP Whisper",
    note: "The HH server's Finnish model today",
    maker: "huggingface",
  },
  {
    id: "hf_whisper-large-v3",
    name: "Whisper large-v3",
    note: "The open model as it is",
    maker: "openai",
  },
  {
    id: "azure_gpt-4o-transcribe",
    name: "gpt-4o-transcribe",
    note: "OpenAI cloud",
    maker: "openai",
  },
  {
    id: "google_chirp-3",
    name: "Chirp 3",
    note: "Google Cloud",
    maker: "google",
  },
];

export interface ModelResult {
  /** The model's words, each with whether the scorer counts it as wrong. */
  words: [string, boolean][];
  errors: number;
  refWords: number;
}

export interface DialectClip {
  id: string;
  place: string;
  /** An English gloss, where one was written. */
  gloss: string;
  /** The human transcript (SKN). */
  reference: string;
  results: Record<ModelId, ModelResult>;
}

export const DIALECT_CLIPS = samples.clips as DialectClip[];

/** Word error rate over all 600 test clips, per model. */
export const DIALECT_AVERAGES = samples.averages as Record<
  ModelId,
  { wer: number; segments: number }
>;

export function clipAudio(clip: DialectClip): string {
  return `/transcriber-examples/dialects/${clip.id}.mp3`;
}

/** Errors per hundred reference words, rounded: 3 errors in 19 words -> 16. */
export function clipWer(result: ModelResult): number {
  return result.refWords > 0
    ? Math.round((100 * result.errors) / result.refWords)
    : 0;
}

export const DIALECT_LINKS = {
  model: "https://huggingface.co/GAIK-project/whisper-large-v3-fi-dialects",
  organisation: "https://huggingface.co/GAIK-project",
  source: "https://github.com/GAIK-project/finnish-asr",
  toolkitDocs:
    "https://github.com/GAIK-project/gaik-toolkit/tree/main/evaluation_layer/eval_methods/transcription_eval/finnish_dialect_asr",
  moreClips: "https://gaik-project.github.io/finnish-asr/listen.html",
  dataset:
    "https://huggingface.co/datasets/GAIK-project/skn-finnish-dialects-asr",
  kielipankki: "http://urn.fi/urn:nbn:fi:lb-2020112937",
};
