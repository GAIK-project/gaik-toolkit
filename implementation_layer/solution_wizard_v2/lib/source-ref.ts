/**
 * A source reference inside a result value. A generated solution that cites
 * its sources writes them as one string per citation, the file's name and
 * where in it, parted by "|":
 *
 * - "meeting.wav|00:00:00|00:01:12": a recording, from and to;
 * - "meeting.wav|00:01:12": a recording, one moment;
 * - "agenda.pdf|2": a document's page.
 *
 * Those exact shapes are read, and only for a name with a known file type;
 * anything else is not a reference and stays as it was written.
 */
import { fileKind } from "@/lib/file-kind";

export type SourceRef = {
  /** The file's name, as written. */
  file: string;
  /** 1-based page, for a document. */
  page: number | null;
  /** "0:00" and "1:12", for a recording; `to` is null for one moment. */
  from: string | null;
  to: string | null;
};

const TIME = /^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:[.,]\d+)?$/;
const PAGE = /^\d{1,5}$/;

/** "00:01:12" as a person writes it: "1:12"; an hour is kept ("1:02:03"). Null for anything else. */
export function shortTime(written: string): string | null {
  const match = TIME.exec(written.trim());
  if (!match) return null;
  const hours = Number(match[1] ?? 0);
  const minutes = Number(match[2]);
  const seconds = match[3];
  if (Number(seconds) > 59 || (match[1] !== undefined && minutes > 59)) return null;
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, "0")}:${seconds}` : `${minutes}:${seconds}`;
}

export function sourceRef(text: string): SourceRef | null {
  const parts = text.split("|").map((part) => part.trim());
  if (parts.length < 2 || parts.length > 3) return null;
  const [file, first, second] = parts;
  if (!file || /[\r\n]/.test(text) || fileKind(file) === null) return null;
  if (second === undefined && PAGE.test(first)) {
    const page = Number(first);
    return page > 0 ? { file, page, from: null, to: null } : null;
  }
  const from = shortTime(first);
  if (from === null) return null;
  if (second === undefined) return { file, page: null, from, to: null };
  const to = shortTime(second);
  return to === null ? null : { file, page: null, from, to };
}

/** Where in the file: "0:00–1:12", "1:12" or the page in the page's words ("p. {n}"). */
export function sourceRefPlace(ref: SourceRef, pageLabel: string): string {
  if (ref.page !== null) return pageLabel.replace("{n}", String(ref.page));
  return ref.to === null ? (ref.from ?? "") : `${ref.from}–${ref.to}`;
}
