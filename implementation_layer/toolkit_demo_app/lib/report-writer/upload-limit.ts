/**
 * Report Writer upload budget, shared by the page and its run route.
 *
 * Runs may carry 100 MiB of file content, the sample report included. A run
 * route reads at most 128 MiB of a request (the report runs' entries in
 * api/upload_limits.json, read through lib/upload-limits.ts) and refuses a
 * larger one as soon as it declares or passes that. The page checks the files
 * against the budget before sending, so the user gets compression advice
 * instead.
 */
import { bodyLimitFor } from "@/lib/upload-limits";

export const REPORT_UPLOAD_MAX_MB = 100;
export const REPORT_UPLOAD_MAX_BYTES = REPORT_UPLOAD_MAX_MB * 1024 * 1024;

/** Whole-request cap of the proxy: the file budget plus multipart and config. */
export const REPORT_REQUEST_MAX_BYTES = 128 * 1024 * 1024;

/**
 * Input files one run may carry: the run's file parts (api/upload_limits.json)
 * less the sample report's. The additional-context text goes as one of them.
 */
export const REPORT_MAX_INPUT_FILES =
  bodyLimitFor("/report-writer/run").maxFiles - 1;

const MEDIA_EXT = /\.(mp3|wav|m4a|aac|flac|ogg|mp4|mov|mkv|avi|webm)$/i;

/** Speech-quality mono MP3: about 14 MB per hour, so ~7 hours fit in 100 MiB. */
export const AUDIO_COMPRESS_COMMAND =
  "ffmpeg -i input.mp4 -vn -ac 1 -ar 16000 -b:a 32k output.mp3";

export const COMPRESS_HINT =
  "Compress audio or video to speech-quality MP3 first (about 14 MB per hour): " +
  AUDIO_COMPRESS_COMMAND;

export function isMediaFile(name: string): boolean {
  return MEDIA_EXT.test(name);
}

/** File content counted against the budget, as the run route counts it. */
export function totalFileBytes(files: { size: number }[]): number {
  return files.reduce((n, f) => n + f.size, 0);
}
