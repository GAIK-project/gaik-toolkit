/**
 * The Wizard V2 address the /solution-wizard notice links to, or null when it is
 * unset or not an absolute http(s) URL, so a mistyped setting shows no link.
 */
export function wizardV2Url(value: string | undefined): string | null {
  const raw = value?.trim();
  if (!raw) return null;
  try {
    const url = new URL(raw);
    return url.protocol === "https:" || url.protocol === "http:"
      ? url.toString()
      : null;
  } catch {
    return null;
  }
}
