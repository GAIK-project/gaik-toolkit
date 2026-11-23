import type { Page } from "@playwright/test";

/** A chat reference as the page dispatches it (lib/chat-events.ts). */
export type RecordedReference = { key: string; label: string; prefix: string; draft?: string };

/**
 * Records the chat references the page dispatches from now on, and returns a
 * reader for them. Tests of a "change this in the chat" button check the event
 * and its detail: what the chat does with it is the chat's own spec.
 */
export async function recordChatReferences(page: Page): Promise<() => Promise<RecordedReference[]>> {
  await page.evaluate(() => {
    const store = window as unknown as { __chatReferences: unknown[] };
    store.__chatReferences = [];
    window.addEventListener("gaik-wizard:chat-reference", (e) => {
      store.__chatReferences.push((e as CustomEvent).detail);
    });
  });
  return () =>
    page.evaluate(
      () => (window as unknown as { __chatReferences: RecordedReference[] }).__chatReferences,
    );
}
