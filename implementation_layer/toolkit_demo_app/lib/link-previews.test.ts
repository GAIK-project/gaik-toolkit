import { afterEach, expect, test } from "bun:test";
import { getGithubPreviewSafe, PREVIEW_TIMEOUT_MS } from "./link-previews";

const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
});

test(
  "a github.com that does not answer gives no preview instead of a hang",
  async () => {
    let signal: AbortSignal | undefined;
    globalThis.fetch = ((_url: string, init?: RequestInit) => {
      signal = init?.signal ?? undefined;
      return new Promise((_resolve, reject) => {
        signal?.addEventListener("abort", () => reject(signal?.reason));
      });
    }) as typeof fetch;

    const started = Date.now();
    expect(await getGithubPreviewSafe()).toBeNull();
    expect(signal).toBeDefined();
    expect(Date.now() - started).toBeLessThan(PREVIEW_TIMEOUT_MS + 2000);
  },
  PREVIEW_TIMEOUT_MS + 5000,
);

test("an answering github.com still gives the preview", async () => {
  globalThis.fetch = (async () =>
    new Response(
      '<title>GAIK toolkit</title><meta name="description" content="Toolkit">',
    )) as unknown as typeof fetch;

  expect(await getGithubPreviewSafe()).toEqual({
    title: "GAIK toolkit",
    description: "Toolkit",
    image: null,
  });
});
