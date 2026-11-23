/**
 * After the run, the sandbox Job prints every output file again, base64, so
 * the api can offer it as a download (sandbox-job.yaml, #314). The api reads
 * that block from the raw log; in the PoC tab's run log it is only noise —
 * thousands of base64 lines that push the run's own output out of the kept
 * tail. These markers bound it (case_service.FILES_BEGIN / FILES_END).
 */
const FILES_BEGIN = "=== POC FILES BEGIN ===";
const FILES_END = "=== POC FILES END ===";

/**
 * A filter for the lines of one run's log, in the order they arrive: false
 * for the files block, its markers included, true for everything else.
 * Stateful, since the block spans many lines; make one per run.
 */
export function runLogLineFilter(): (line: string) => boolean {
  let inFiles = false;
  return (line) => {
    if (line.startsWith(FILES_BEGIN)) {
      inFiles = true;
      return false;
    }
    if (inFiles) {
      if (line.startsWith(FILES_END)) inFiles = false;
      return false;
    }
    return true;
  };
}

export type LogLineTone = "error" | "ok" | "normal";

const REAL_ERROR_LINE =
  /✗|\btraceback\b|\b(?:[a-z_]+error|exception)\s*:|^\s*(?:error|fatal|critical)\b|\bfailed\b|\bfailure\b/i;

const OK_LINE = /✓|\bsuccess(?:fully|ful)?\b|\bok\b/i;

/**
 * Classifies one sandbox log line for colour coding. Benign progress messages
 * such as "Fixing transcription errors with TranscriptEnhancer..." stay normal
 * instead of flashing red as if the run had failed (#252).
 */
export function classifyLogLine(line: string): LogLineTone {
  // Only real failure markers turn a line red; a progress line that merely says
  // "errors" ("Fixing transcription errors…", "0 errors found") never matches them.
  if (REAL_ERROR_LINE.test(line)) return "error";
  if (OK_LINE.test(line)) return "ok";
  return "normal";
}

export type RunProgressStage =
  | "queued"
  | "starting"
  | "transcribing"
  | "enhancing"
  | "parsing"
  | "extracting"
  | "validating"
  | "finalizing"
  | "working";

/**
 * Maps the live sandbox phase and recent log lines to a calm, plain-language
 * progress stage shown beside the result while technical logs stay in a
 * disclosure (#252).
 */
export function runProgressStage(phase: string, logs: readonly string[]): RunProgressStage {
  if (phase === "pending") return "queued";
  for (let i = logs.length - 1; i >= 0; i--) {
    const line = logs[i];
    if (/===\s*poc output|writing output|saving (?:result|output|report|pdf)|generat(?:ing|ed) (?:pdf|report)/i.test(line)) {
      return "finalizing";
    }
    if (/grounding|hallucinat|validat(?:ing|ion)|verif(?:y|ying|ication)|source.?trac/i.test(line)) {
      return "validating";
    }
    if (/extract(?:ing|or|ion)|structured output|schema/i.test(line)) {
      return "extracting";
    }
    if (/transcriptenhancer|fixing transcription|enhanc(?:ing|e)\s+transcript/i.test(line)) {
      return "enhancing";
    }
    if (/transcrib(?:ing|er|e)|whisper|audio|speech/i.test(line)) {
      return "transcribing";
    }
    if (/pars(?:ing|er|e)|vision|reading (?:pdf|doc|file|input)|loading (?:document|file)/i.test(line)) {
      return "parsing";
    }
    if (/installing|pip |uv |starting|loading config|initializing/i.test(line)) {
      return "starting";
    }
  }
  return logs.length === 0 ? "starting" : "working";
}
