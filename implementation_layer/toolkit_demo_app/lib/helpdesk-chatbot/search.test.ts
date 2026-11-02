import { expect, test } from "bun:test";
import { HELPDESK_EXAMPLES, getHelpdeskExample } from "./examples";
import { HUB_KNOWLEDGE } from "./knowledge";
import { IT_KNOWLEDGE } from "./knowledge-it";
import { searchArticles, searchServices, tokenize } from "./search";

test("tokenize drops stopwords and punctuation", () => {
  expect(tokenize("How do I get started?")).toEqual(["get", "started"]);
});

test("a filter decides the set, words only the order", () => {
  const all = searchServices(HUB_KNOWLEDGE, { category: "training" });
  const ranked = searchServices(HUB_KNOWLEDGE, {
    category: "training",
    query: "AI Act law",
  });
  expect(ranked.map((s) => s.id).sort()).toEqual(all.map((s) => s.id).sort());
  expect(ranked[0].id).toBe("ai-act-briefing");
});

test("no filter returns the whole catalogue", () => {
  expect(searchServices(HUB_KNOWLEDGE, { query: "anything" })).toHaveLength(
    HUB_KNOWLEDGE.services.length,
  );
});

test("audience filter excludes services not offered to it", () => {
  const ids = searchServices(HUB_KNOWLEDGE, { audience: "public-sector" }).map(
    (s) => s.id,
  );
  expect(ids).not.toContain("rapid-poc");
  expect(ids).toContain("ai-act-briefing");
});

test("prefix matching finds plural and inflected forms", () => {
  expect(searchServices(HUB_KNOWLEDGE, { query: "invoice" })[0].id).toBe(
    "document-automation-pilot",
  );
  expect(searchArticles(HUB_KNOWLEDGE, "opening hour")[0].id).toBe(
    "opening-hours",
  );
});

test("an unrelated query finds no articles", () => {
  expect(searchArticles(HUB_KNOWLEDGE, "football results")).toEqual([]);
});

// The IT and HR helpdesk answers from its own knowledge, not the hub's.
test("the IT helpdesk finds its own services and articles", () => {
  expect(
    searchServices(IT_KNOWLEDGE, { audience: "new-hire", query: "laptop" })[0]
      .id,
  ).toBe("new-hire-kit");
  expect(searchArticles(IT_KNOWLEDGE, "vpn disconnects")[0].id).toBe(
    "vpn-tips",
  );
  expect(searchServices(HUB_KNOWLEDGE, { query: "vpn" })[0].id).not.toBe(
    "vpn-access",
  );
});

// Keyword search still returns articles that mention the "service desk" for a
// "standing desk" question, so the assistant has to notice that none of them
// covers furniture or reimbursement. The knowledge must not cover them.
test("the IT helpdesk does not cover standing desks, which a person must answer", () => {
  const hits = searchArticles(IT_KNOWLEDGE, "standing desk reimbursed");
  expect(
    hits.some((a) => /standing|reimburs|furniture|ergonomic/i.test(a.body)),
  ).toBe(false);
  expect(IT_KNOWLEDGE.teams.workplace.handles).toContain("desks");
});

// Each knowledge must be consistent, or the tools and the cards would break.
for (const example of HELPDESK_EXAMPLES) {
  const { knowledge } = example;

  test(`${example.id}: services use declared categories, audiences and teams`, () => {
    const ids = new Set<string>();
    for (const s of knowledge.services) {
      expect(ids.has(s.id)).toBe(false);
      ids.add(s.id);
      expect(knowledge.categories).toContain(s.category);
      expect(Object.keys(knowledge.categoryLabels)).toContain(s.category);
      expect(knowledge.teams[s.team]).toBeDefined();
      for (const a of s.audiences) expect(knowledge.audiences).toContain(a);
    }
  });

  test(`${example.id}: articles have unique ids`, () => {
    const ids = knowledge.articles.map((a) => a.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  test(`${example.id}: the scripted demo uses real teams and finds results`, () => {
    const { demo } = example;
    expect(knowledge.teams[demo.handoff.team]).toBeDefined();
    expect(
      searchServices(knowledge, demo.servicesInput).length,
    ).toBeGreaterThan(0);
    expect(searchArticles(knowledge, demo.faqQuery).length).toBeGreaterThan(0);
  });

  test(`${example.id}: it offers four starter questions`, () => {
    expect(example.starters).toHaveLength(4);
  });
}

test("examples are found by id, and an unknown id is not", () => {
  expect(getHelpdeskExample("it-hr")?.knowledge).toBe(IT_KNOWLEDGE);
  expect(getHelpdeskExample("ai-hub")?.knowledge).toBe(HUB_KNOWLEDGE);
  expect(getHelpdeskExample("nope")).toBeUndefined();
  expect(getHelpdeskExample(undefined)).toBeUndefined();
});
