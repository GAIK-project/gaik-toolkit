import { afterEach, expect, mock, test } from "bun:test";
import { downloadBlob, REVOKE_DELAY_MS } from "./download";

const g = globalThis as unknown as Record<string, unknown>;
const saved = { document: g.document, createObjectURL: URL.createObjectURL, revokeObjectURL: URL.revokeObjectURL };

afterEach(() => {
  g.document = saved.document;
  URL.createObjectURL = saved.createObjectURL;
  URL.revokeObjectURL = saved.revokeObjectURL;
});

/** A minimal DOM: records the anchor and whether it was attached when clicked. */
function fakeBrowser() {
  const events: string[] = [];
  const anchor = {
    href: "",
    download: "",
    style: { display: "" },
    click: () => events.push(`click attached=${attached}`),
    remove: () => {
      attached = false;
      events.push("remove");
    },
  };
  let attached = false;
  g.document = {
    createElement: () => anchor,
    body: {
      appendChild: () => {
        attached = true;
        events.push("append");
      },
    },
  };
  const blobs: Blob[] = [];
  URL.createObjectURL = ((b: Blob) => {
    blobs.push(b);
    return "blob:test-url";
  }) as typeof URL.createObjectURL;
  const revoked = mock(() => {});
  URL.revokeObjectURL = revoked;
  return { anchor, events, blobs, revoked };
}

test("the anchor carries the file name and is attached while clicked", () => {
  const { anchor, events } = fakeBrowser();

  downloadBlob("hello", "normalized.zip", "application/zip");

  expect(anchor.download).toBe("normalized.zip");
  expect(anchor.href).toBe("blob:test-url");
  expect(events).toEqual(["append", "click attached=true", "remove"]);
});

test("the blob has the given type, defaulting to a binary type", () => {
  const { blobs } = fakeBrowser();

  downloadBlob("a", "a.zip", "application/zip");
  downloadBlob("b", "b.bin");

  expect(blobs.map((b) => b.type)).toEqual(["application/zip", "application/octet-stream"]);
});

test("the object URL is revoked later, not right after the click", async () => {
  const { revoked } = fakeBrowser();
  const timers: { fn: () => void; ms: number }[] = [];
  const realSetTimeout = globalThis.setTimeout;
  globalThis.setTimeout = ((fn: () => void, ms: number) => {
    timers.push({ fn, ms });
    return 0;
  }) as unknown as typeof setTimeout;
  try {
    downloadBlob("x", "x.zip");
  } finally {
    globalThis.setTimeout = realSetTimeout;
  }

  expect(revoked).not.toHaveBeenCalled();
  expect(timers).toHaveLength(1);
  expect(timers[0].ms).toBe(REVOKE_DELAY_MS);
  timers[0].fn();
  expect(revoked).toHaveBeenCalledWith("blob:test-url");
});
