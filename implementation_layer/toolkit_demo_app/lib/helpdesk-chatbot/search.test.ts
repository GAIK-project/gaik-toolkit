import { expect, test } from "bun:test";
import { SERVICES } from "./knowledge";
import { searchArticles, searchServices, tokenize } from "./search";

test("tokenize drops stopwords and punctuation", () => {
  expect(tokenize("How do I get started?")).toEqual(["get", "started"]);
});

test("a filter decides the set, words only the order", () => {
  const all = searchServices({ category: "training" });
  const ranked = searchServices({ category: "training", query: "AI Act law" });
  expect(ranked.map((s) => s.id).sort()).toEqual(all.map((s) => s.id).sort());
  expect(ranked[0].id).toBe("ai-act-briefing");
});

test("no filter returns the whole catalogue", () => {
  expect(searchServices({ query: "anything" })).toHaveLength(SERVICES.length);
});

test("audience filter excludes services not offered to it", () => {
  const ids = searchServices({ audience: "public-sector" }).map((s) => s.id);
  expect(ids).not.toContain("rapid-poc");
  expect(ids).toContain("ai-act-briefing");
});

test("prefix matching finds plural and inflected forms", () => {
  expect(searchServices({ query: "invoice" })[0].id).toBe(
    "document-automation-pilot",
  );
  expect(searchArticles("opening hour")[0].id).toBe("opening-hours");
});

test("an unrelated query finds no articles", () => {
  expect(searchArticles("football results")).toEqual([]);
});
