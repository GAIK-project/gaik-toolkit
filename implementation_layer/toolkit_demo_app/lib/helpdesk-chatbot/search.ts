// Keyword search over the demo knowledge. It ranks rather than filters by text:
// the catalogue is small and finite, so a structured filter (category,
// audience) decides what is returned and the words only decide the order. A
// text filter would make the result set depend on how the model phrased the
// query, and the same question would get different answers from run to run.

import {
  ARTICLES,
  type Article,
  type Audience,
  SERVICES,
  type Service,
  type ServiceCategory,
} from "./knowledge";

const STOPWORDS = new Set(
  "a an and are as at be by can do does for from how i in is it me my of on or our that the this to we what when where which who why will with you your".split(
    " ",
  ),
);

export function tokenize(text: string): string[] {
  return (text.toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? []).filter(
    (word) => word.length > 1 && !STOPWORDS.has(word),
  );
}

// "invoice" matches "invoices" and "fund" matches "funding": a shared prefix of
// four letters or more counts as a hit, which covers most plural and verb forms.
function matches(queryWord: string, word: string): boolean {
  if (queryWord === word) return true;
  const shorter = queryWord.length < word.length ? queryWord : word;
  const longer = shorter === queryWord ? word : queryWord;
  return shorter.length >= 4 && longer.startsWith(shorter);
}

function score(query: string[], fields: [string, number][]): number {
  let total = 0;
  for (const [text, weight] of fields) {
    const words = tokenize(text);
    for (const q of query) {
      if (words.some((w) => matches(q, w))) total += weight;
    }
  }
  return total;
}

function serviceScore(service: Service, query: string[]): number {
  return score(query, [
    [service.name, 3],
    [service.tags.join(" "), 2],
    [`${service.summary} ${service.details}`, 1],
  ]);
}

export interface ServiceFilters {
  category?: ServiceCategory;
  audience?: Audience;
  query?: string;
}

/** Every service that passes the filters, best text match first. */
export function searchServices({
  category,
  audience,
  query,
}: ServiceFilters): Service[] {
  const words = tokenize(query ?? "");
  return SERVICES.filter(
    (s) =>
      (!category || s.category === category) &&
      (!audience || s.audiences.includes(audience)),
  )
    .map((service, index) => ({
      service,
      index,
      score: serviceScore(service, words),
    }))
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .map(({ service }) => service);
}

/** The articles that share at least one word with the query, best first. */
export function searchArticles(query: string, limit = 3): Article[] {
  const words = tokenize(query);
  return ARTICLES.map((article) => ({
    article,
    score: score(words, [
      [article.title, 3],
      [article.tags.join(" "), 2],
      [article.body, 1],
    ]),
  }))
    .filter(({ score }) => score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map(({ article }) => article);
}
