import type { APIRequestContext } from "@playwright/test";

/** Reset in-memory mock sessions between E2E tests (dev auth only). */
export async function resetMockSessions(request: APIRequestContext) {
  // The dev server now and then resets a connection when the test before
  // closed its page in the middle of a stream ("read ECONNRESET" on this very
  // request, before the test had begun). The reset has no partial effect to
  // fear, so a request that never got an answer is sent once more; an answer
  // that says no is still a failure.
  const res = await request.post("/api/dev/reset-mocks").catch(() => request.post("/api/dev/reset-mocks"));
  if (!res.ok()) {
    throw new Error(`reset-mocks failed: ${res.status()} ${await res.text()}`);
  }
  const body = (await res.json()) as { ok?: boolean };
  if (!body.ok) {
    throw new Error("reset-mocks returned unexpected body");
  }
}
