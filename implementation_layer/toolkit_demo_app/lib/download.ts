/** How long the object URL stays valid: the browser reads it when the download starts. */
export const REVOKE_DELAY_MS = 10_000;

/**
 * Save `data` as a file called `name`.
 *
 * The anchor is attached to the page while it is clicked, and the object URL is revoked
 * only later. Revoking it right after `click()` can happen before Chrome has started
 * the download, which then saves the file under a random name without an extension.
 */
export function downloadBlob(
  data: BlobPart,
  name: string,
  type = "application/octet-stream",
): void {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), REVOKE_DELAY_MS);
}
