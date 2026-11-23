/** Where the wizard's people come from: the GAIK toolkit's demos. */
const DEFAULT_DEMO_URL = "https://gaik-demo.2.rahtiapp.fi";

/**
 * The address of the GAIK demos, which the sign-in page and the account menu
 * link back to. Read on the server when a page is drawn, so an instance can
 * change it without a new build: `GAIK_DEMO_URL` sets it, an empty value hides
 * the link, and anything but an http(s) address hides it too.
 */
export function gaikDemoUrl(value: string | undefined = process.env.GAIK_DEMO_URL): string | null {
  const raw = value === undefined ? DEFAULT_DEMO_URL : value.trim();
  if (!raw) return null;
  try {
    const url = new URL(raw);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}
