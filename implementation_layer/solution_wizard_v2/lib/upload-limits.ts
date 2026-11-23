/**
 * What an upload route decides from the request before reading its body (#297).
 *
 * `req.formData()` buffers the whole body, so the size must be settled first.
 * A request without a content-length (a chunked body) said nothing, skipped
 * the check and was buffered whole; it is refused now, since every browser
 * and client that sends a form says its length.
 */

export const MAX_INPUT_BYTES = 50 * 1024 * 1024;

/**
 * What a multipart request may carry beyond the file itself: boundaries, part
 * headers and the small text fields. The declared length is the whole request,
 * so a file just under the limit must not be refused for this overhead; the
 * file's own size is checked exactly once the form is read.
 */
export const MULTIPART_ALLOWANCE_BYTES = 64 * 1024;

export type UploadRefusal = { status: number; detail: string };

/** Null when the declared length is acceptable; else the refusal to answer with. */
export function declaredLengthProblem(
  contentLength: string | null,
  max: number = MAX_INPUT_BYTES,
  allowance: number = MULTIPART_ALLOWANCE_BYTES,
): UploadRefusal | null {
  const declared = Number(contentLength);
  if (contentLength === null || contentLength.trim() === "" || !Number.isFinite(declared) || declared < 0) {
    return { status: 411, detail: "send the upload with a content-length" };
  }
  if (declared > max + allowance) return { status: 413, detail: `the file is larger than ${Math.floor(max / (1024 * 1024))} MB` };
  return null;
}

/** The same refusal for the file itself, once the form is read. */
export function fileSizeProblem(size: number, max: number = MAX_INPUT_BYTES): UploadRefusal | null {
  return size > max ? { status: 413, detail: `the file is larger than ${Math.floor(max / (1024 * 1024))} MB` } : null;
}
