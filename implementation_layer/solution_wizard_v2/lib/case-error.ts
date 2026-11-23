/**
 * What the case view says when the api refuses something.
 *
 * The api answers in English ("this file type is not accepted here; accepted
 * types: WAV, MP3, M4A, JSON"), and the view showed that under a Finnish page.
 * The refusals a person meets while adding a file are said in the page's
 * language from their code; the rest keep the api's words, which name the
 * case's own state.
 */

import type { CaseStrings } from "@/lib/case-strings";
import { isSandboxBusy } from "@/lib/sandbox-busy";
import { MAX_INPUT_BYTES } from "@/lib/upload-limits";

export type AcceptedInput = { kind?: string; label: string; extensions: string[] };

/** "WAV, MP3, M4A tai JSON": the accepted types as one phrase. */
export function acceptedPhrase(accepted: AcceptedInput[], or: string): string {
  const labels = accepted.map((a) => a.label);
  if (labels.length < 2) return labels.join("");
  return `${labels.slice(0, -1).join(", ")} ${or} ${labels.at(-1)}`;
}

/** The file input's `accept` value; empty when the api named no types. */
export function acceptAttribute(accepted: AcceptedInput[]): string {
  return accepted.flatMap((a) => a.extensions).join(",");
}

/** The types an older api names only in its refusal ("...; accepted types: WAV, MP3"). */
function acceptedFromMessage(message: string): AcceptedInput[] {
  const listed = /accepted types: ([A-Za-z0-9, ]+)/.exec(message)?.[1] ?? "";
  return listed
    .split(",")
    .map((label) => label.trim())
    .filter(Boolean)
    .map((label) => ({ label, extensions: [] }));
}

function detailMessage(detail: unknown): string {
  return detail && typeof detail === "object" ? String((detail as { message?: unknown }).message ?? "") : "";
}

/** The api gives input_unsafe for the malware check and for a document's own content. */
function unsafeText(message: string, s: CaseStrings): string {
  if (message.includes("macros")) return s.errors.macros;
  if (message.includes("encrypted") || message.includes("password")) return s.errors.encrypted;
  if (message.includes("too complex") || message.includes("too large") || message.includes("damaged")) {
    return s.errors.uncheckable;
  }
  if (message.startsWith("PDF files that contain")) return s.errors.activeContent;
  return s.errors.unsafe;
}

export function caseErrorText(
  status: number,
  body: unknown,
  s: CaseStrings,
  busyMessage: string,
  accepted: AcceptedInput[] = [],
): string {
  // The api's busy text names stack-wide counts; the user sees the localized one.
  if (isSandboxBusy(status, body)) return busyMessage;
  const detail = (body as { detail?: unknown } | null)?.detail;
  const code = detail && typeof detail === "object" ? String((detail as { error?: unknown }).error ?? "") : "";
  if (code === "input_type_not_accepted") {
    const message = String((detail as { message?: unknown }).message ?? "");
    // The api gives this code for two refusals: a type the step does not take,
    // and a file whose content is not what its extension says.
    const problem = message.includes("does not match") ? s.errors.contentMismatch : s.errors.typeNotAccepted;
    const types = acceptedPhrase(accepted.length ? accepted : acceptedFromMessage(message), s.or);
    return types ? `${problem} ${s.acceptedTypes}: ${types}.` : problem;
  }
  if (code === "input_too_large" || status === 413) {
    // One code for three limits: the file's own size, the case's inputs in all,
    // and the session's. Only the first is cured by a smaller file.
    const message = detail && typeof detail === "object" ? String((detail as { message?: unknown }).message ?? "") : "";
    const total = /exceed (\d+) MB in all/.exec(message)?.[1];
    if (total) return (message.includes("session") ? s.errors.sessionFull : s.errors.caseFull).replace("{mb}", total);
    return s.errors.tooLarge.replace("{mb}", String(Math.floor(MAX_INPUT_BYTES / (1024 * 1024))));
  }
  if (code === "input_exists") return s.errors.exists;
  if (code === "input_unsafe") return unsafeText(detailMessage(detail), s);
  if (code === "scanner_unavailable") return s.errors.scanUnavailable;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  return `HTTP ${status}`;
}
