import type { HybridSearchOptions, HybridSearchResult, PoolLike } from './types.js';

function formatVector(embedding: number[]): string {
  return `[${embedding.join(',')}]`;
}

/** Perform hybrid search combining semantic and keyword search */
export async function hybridSearch(
  pool: PoolLike,
  options: HybridSearchOptions
): Promise<HybridSearchResult[]> {
  const {
    tableName,
    queryText,
    queryEmbedding,
    limit = 20,
    semanticWeight = 0.5,
    keywordWeight = 0.5,
    rrfK = 60,
  } = options;

  const result = await pool.query(`SELECT * FROM gaik_hybrid_search($1, $2, $3::vector, $4, $5, $6, $7)`, [
    tableName,
    queryText ?? null,
    queryEmbedding ? formatVector(queryEmbedding) : null,
    limit,
    semanticWeight,
    keywordWeight,
    rrfK,
  ]);

  return (
    result.rows as Array<{
      id: string | number;
      content: string;
      semantic_rank: number | null;
      keyword_rank: number | null;
      rrf_score: number;
      metadata?: Record<string, unknown>;
    }>
  ).map((row) => ({
    id: row.id,
    content: row.content,
    semanticRank: row.semantic_rank,
    keywordRank: row.keyword_rank,
    rrfScore: row.rrf_score,
    metadata: row.metadata,
  }));
}

/** Keyword-only search */
export async function keywordSearch(
  pool: PoolLike,
  tableName: string,
  queryText: string,
  options: { limit?: number } = {}
): Promise<HybridSearchResult[]> {
  return hybridSearch(pool, {
    tableName,
    queryText,
    queryEmbedding: undefined,
    limit: options.limit,
    semanticWeight: 0,
    keywordWeight: 1,
  });
}

/** Semantic-only search via hybrid function */
export async function semanticOnlySearch(
  pool: PoolLike,
  tableName: string,
  queryEmbedding: number[],
  options: { limit?: number } = {}
): Promise<HybridSearchResult[]> {
  return hybridSearch(pool, {
    tableName,
    queryText: undefined,
    queryEmbedding,
    limit: options.limit,
    semanticWeight: 1,
    keywordWeight: 0,
  });
}

/** Reciprocal Rank Fusion - combine multiple ranked lists */
export function reciprocalRankFusion<T>(rankedLists: T[][], k = 60): Map<T, number> {
  const scores = new Map<T, number>();

  for (const list of rankedLists) {
    for (let rank = 0; rank < list.length; rank++) {
      const item = list[rank];
      const rrfScore = 1 / (k + rank + 1);
      const currentScore = scores.get(item) ?? 0;
      scores.set(item, currentScore + rrfScore);
    }
  }

  return scores;
}

/** Re-rank results using a custom scoring function */
export function rerank<T extends { id: string | number }>(
  results: T[],
  scoreFn: (item: T) => number
): (T & { rerankedScore: number })[] {
  return results
    .map((item) => ({ ...item, rerankedScore: scoreFn(item) }))
    .sort((a, b) => b.rerankedScore - a.rerankedScore);
}
