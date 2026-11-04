import { describe, expect, test } from "bun:test";
import {
  type Citation,
  INITIAL_STATE,
  type RunState,
  citationsByCell,
  citationsPerPage,
  crawlMarkdown,
  inDomains,
  pageOfRow,
  reduceRun,
  tableOf,
} from "./scraper-data";

function run(
  events: { type: string; data?: Record<string, unknown> }[],
): RunState {
  return events.reduce(
    (state, event) =>
      reduceRun(
        state,
        event.data ? { type: event.type, data: event.data } : { type: "start" },
      ),
    INITIAL_STATE,
  );
}

describe("reduceRun", () => {
  test("a request becomes a page, a redirect alias is dropped at the end", () => {
    const state = run([
      { type: "start" },
      {
        type: "request",
        data: { url: "https://x.fi/", depth: 0, parent_url: null },
      },
      {
        type: "page",
        data: {
          url: "https://x.fi/",
          final_url: "https://x.fi/",
          title: "Home",
          word_count: 9,
        },
      },
      {
        type: "request",
        data: {
          url: "https://x.fi/old",
          depth: 1,
          parent_url: "https://x.fi/",
        },
      },
      {
        type: "crawl_done",
        data: { pages: 1, skipped: 0, words: 9, duration_s: 1.2 },
      },
    ]);
    expect(state.nodes.map((n) => [n.url, n.status, n.title])).toEqual([
      ["https://x.fi/", "page", "Home"],
    ]);
    expect(state.stats).toEqual({
      pages: 1,
      skipped: 0,
      words: 9,
      durationS: 1.2,
    });
    expect(state.phase).toBe("done");
  });

  test("a skipped URL keeps its reason; an error ends the run", () => {
    const state = run([
      { type: "start" },
      {
        type: "request",
        data: { url: "https://x.fi/a", depth: 1, parent_url: "https://x.fi/" },
      },
      {
        type: "skipped",
        data: { url: "https://x.fi/a", reason: "HTTP 404", depth: 1 },
      },
      { type: "error", data: { message: "boom" } },
    ]);
    expect(state.nodes[0]).toMatchObject({
      status: "skipped",
      reason: "HTTP 404",
    });
    expect(state).toMatchObject({ phase: "error", error: "boom" });
  });

  test("start clears an earlier run", () => {
    const state = run([
      { type: "start" },
      { type: "request", data: { url: "https://x.fi/" } },
      { type: "start" },
    ]);
    expect(state.nodes).toEqual([]);
    expect(state.phase).toBe("crawling");
  });
});

const SOURCES: Citation[] = [
  {
    field: "events[0].title",
    quote: "A",
    value: "A",
    verdict: "verified",
    record: 0,
    page_url: "https://x.fi/news",
  },
  {
    field: "events[0].date",
    quote: "1.1.",
    value: "2026-01-01",
    verdict: "check",
    record: 0,
    page_url: "https://x.fi/news",
  },
  {
    field: "events[1].title",
    quote: "B",
    value: "B",
    verdict: "verified",
    record: 1,
    page_url: "https://x.fi/",
  },
  {
    field: "organisation",
    quote: "X",
    value: "X",
    verdict: "verified",
    record: null,
    page_url: null,
  },
];

describe("records and citations", () => {
  test("tableOf unwraps the one list of records", () => {
    const table = tableOf([
      {
        events: [
          { title: "A", date: "x" },
          { title: "B", place: "y" },
        ],
      },
    ]);
    expect(table).toEqual({
      key: "events",
      columns: ["title", "date", "place"],
      rows: [
        { title: "A", date: "x" },
        { title: "B", place: "y" },
      ],
    });
  });

  test("tableOf keeps flat records as rows", () => {
    expect(tableOf([{ name: "A" }]).rows).toEqual([{ name: "A" }]);
  });

  test("citations by cell, per page and per row", () => {
    const cells = citationsByCell(SOURCES);
    expect(cells.get("0:title")?.quote).toBe("A");
    expect(cells.get("0:date")?.verdict).toBe("check");
    expect(cells.size).toBe(3);
    expect(citationsPerPage(SOURCES)).toEqual({
      "https://x.fi/news": 2,
      "https://x.fi/": 1,
    });
    expect(pageOfRow(SOURCES, 0)).toBe("https://x.fi/news");
    expect(pageOfRow(SOURCES, 5)).toBeNull();
  });
});

describe("helpers", () => {
  test("inDomains allows subdomains, not lookalikes or other schemes", () => {
    expect(inDomains("https://www.haaga-helia.fi/fi", ["haaga-helia.fi"])).toBe(
      true,
    );
    expect(
      inDomains("https://haaga-helia.fi.evil.com/", ["haaga-helia.fi"]),
    ).toBe(false);
    expect(inDomains("https://evilhaaga-helia.fi/", ["haaga-helia.fi"])).toBe(
      false,
    );
    expect(inDomains("ftp://gaik.ai/", ["gaik.ai"])).toBe(false);
    expect(inDomains("not a url", ["gaik.ai"])).toBe(false);
  });

  test("crawlMarkdown heads each page with its source", () => {
    const md = crawlMarkdown([
      {
        url: "u",
        finalUrl: "https://x.fi/",
        parent: null,
        depth: 0,
        status: "page",
        order: 0,
        title: "Home",
        markdown: "Hi",
      },
      {
        url: "v",
        finalUrl: "https://x.fi/v",
        parent: null,
        depth: 1,
        status: "skipped",
        order: 1,
      },
    ]);
    expect(md).toBe("# Home\n\nSource: https://x.fi/\n\nHi\n");
  });
});
