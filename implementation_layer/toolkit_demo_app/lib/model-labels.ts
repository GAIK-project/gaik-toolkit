/** Readable names for the model ids the API reports after a run. */

const NAMES: Record<string, string> = {
  "gpt-4o-transcribe": "GPT-4o Transcribe",
  whisper: "OpenAI Whisper",
  "whisper-1": "OpenAI Whisper",
  // HH's own GPU Whisper server; Finnish uses a Finnish fine-tune of large-v3.
  whisper_local: "Whisper on GAIK's server",
};

/** gpt-6.1-sol -> GPT-6.1 Sol, claude-haiku-5-5 -> Claude Haiku 5.5, gemini-3.8-flash -> Gemini 3.8 Flash. */
export function modelLabel(id: string | null | undefined): string | null {
  if (!id) return null;
  const known = NAMES[id];
  if (known) return known;
  const parts = id.split("/").pop()!.split("-");
  const words: string[] = [];
  parts.forEach((part, index) => {
    const last = words[words.length - 1];
    if (index === 1 && parts[0].toLowerCase() === "gpt") {
      words[0] = `GPT-${part}`;
    } else if (/^\d+$/.test(part) && last && /^[\d.]+$/.test(last)) {
      words[words.length - 1] = `${last}.${part}`;
    } else if (/\d/.test(part)) {
      words.push(part);
    } else {
      words.push(part.charAt(0).toUpperCase() + part.slice(1));
    }
  });
  return words.join(" ");
}

/** "in 13.0 s, transcribed by Whisper on GAIK's server, extracted by GPT-6 Luna" */
export function runSummary(
  seconds: number | null,
  run: {
    transcription_model?: string | null;
    extraction_model?: string | null;
  },
): string | null {
  const parts: string[] = [];
  if (seconds !== null) parts.push(`in ${seconds.toFixed(1)} s`);
  const transcriber = modelLabel(run.transcription_model);
  if (transcriber) parts.push(`transcribed by ${transcriber}`);
  const extractor = modelLabel(run.extraction_model);
  if (extractor) parts.push(`extracted by ${extractor}`);
  return parts.length ? parts.join(", ") : null;
}
