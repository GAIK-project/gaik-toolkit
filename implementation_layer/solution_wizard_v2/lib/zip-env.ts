/**
 * The deployable package with the user's `.env` added, made in the browser.
 *
 * API keys never reach the server: wizard_api refuses to keep a `.env`, and
 * the zip it serves has none. The PoC tab fetches that zip, adds `poc/.env`
 * here and saves the result. fflate is loaded when a download asks for it.
 */

export const ENV_PATH_IN_PACKAGE = "poc/.env";

/** `zip` with `envText` as `poc/.env`, replacing a file of that name. Every other entry is kept. */
export async function zipWithEnv(
  zip: Uint8Array,
  envText: string,
  path: string = ENV_PATH_IN_PACKAGE,
): Promise<Uint8Array> {
  const { unzipSync, zipSync, strToU8 } = await import("fflate");
  const entries = unzipSync(zip);
  entries[path] = strToU8(envText);
  return zipSync(entries, { level: 6 });
}

/** Hand `bytes` to the browser as a download named `filename`. */
export function saveBytes(bytes: Uint8Array, filename: string, type = "application/zip"): void {
  // A copy with its own buffer: a view into a larger one would save the rest too.
  const url = URL.createObjectURL(new Blob([bytes.slice().buffer], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // After the click has been taken: revoking at once cancels the download in some browsers.
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** The file name a `Content-Disposition: attachment; filename="..."` header gives, or `fallback`. */
export function attachmentName(header: string | null, fallback: string): string {
  const match = /filename="([^"\\/]+)"/.exec(header ?? "");
  return match ? match[1] : fallback;
}
