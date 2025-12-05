import type { PoolLike, SemanticSearchOptions, VectorSearchResult } from './types.js';

function formatVector(embedding: number[]): string {
  return `[${embedding.join(',')}]`;
}

/** Perform semantic search using vector similarity */
export async function semanticSearch(
  pool: PoolLike,
  options: SemanticSearchOptions
): Promise<VectorSearchResult[]> {
  const { tableName, queryEmbedding, limit = 20, minSimilarity = 0 } = options;

  const result = await pool.query(`SELECT * FROM gaik_semantic_search($1, $2::vector, $3, $4)`, [
    tableName,
    formatVector(queryEmbedding),
    limit,
    minSimilarity,
  ]);

  return (
    result.rows as Array<{
      id: string | number;
      content: string;
      similarity: number;
      distance: number;
      metadata?: Record<string, unknown>;
    }>
  ).map((row) => ({
    id: row.id,
    content: row.content,
    similarity: row.similarity,
    distance: row.distance,
    metadata: row.metadata,
  }));
}

/** Semantic search with custom table structure */
export async function semanticSearchCustom(
  pool: PoolLike,
  options: SemanticSearchOptions & {
    contentColumn?: string;
    embeddingColumn?: string;
    metadataColumn?: string;
    idColumn?: string;
  }
): Promise<VectorSearchResult[]> {
  const {
    tableName,
    queryEmbedding,
    limit = 20,
    minSimilarity = 0,
    contentColumn = 'content',
    embeddingColumn = 'embedding',
    metadataColumn = 'metadata',
    idColumn = 'id',
  } = options;

  const vectorStr = formatVector(queryEmbedding);

  const sql = `
    SELECT
      ${idColumn} AS id,
      ${contentColumn} AS content,
      (1 - (${embeddingColumn} <=> $1::vector)) AS similarity,
      (${embeddingColumn} <=> $1::vector) AS distance,
      ${metadataColumn} AS metadata
    FROM ${tableName}
    WHERE ${embeddingColumn} IS NOT NULL
      AND (1 - (${embeddingColumn} <=> $1::vector)) >= $3
    ORDER BY ${embeddingColumn} <=> $1::vector
    LIMIT $2
  `;

  const result = await pool.query(sql, [vectorStr, limit, minSimilarity]);

  return (
    result.rows as Array<{
      id: string | number;
      content: string;
      similarity: string | number;
      distance: string | number;
      metadata?: Record<string, unknown>;
    }>
  ).map((row) => ({
    id: row.id,
    content: row.content,
    similarity: typeof row.similarity === 'string' ? parseFloat(row.similarity) : row.similarity,
    distance: typeof row.distance === 'string' ? parseFloat(row.distance) : row.distance,
    metadata: row.metadata,
  }));
}

/** Find similar documents to a given document */
export async function findSimilar(
  pool: PoolLike,
  documentId: string | number,
  tableName: string,
  options: {
    limit?: number;
    minSimilarity?: number;
    embeddingColumn?: string;
    idColumn?: string;
  } = {}
): Promise<VectorSearchResult[]> {
  const { limit = 10, minSimilarity = 0, embeddingColumn = 'embedding', idColumn = 'id' } = options;

  const sql = `
    WITH source AS (
      SELECT ${embeddingColumn} AS embedding
      FROM ${tableName}
      WHERE ${idColumn} = $1
    )
    SELECT
      t.${idColumn} AS id,
      t.content,
      (1 - (t.${embeddingColumn} <=> source.embedding)) AS similarity,
      (t.${embeddingColumn} <=> source.embedding) AS distance,
      t.metadata
    FROM ${tableName} t, source
    WHERE t.${idColumn} != $1
      AND t.${embeddingColumn} IS NOT NULL
      AND (1 - (t.${embeddingColumn} <=> source.embedding)) >= $3
    ORDER BY t.${embeddingColumn} <=> source.embedding
    LIMIT $2
  `;

  const result = await pool.query(sql, [documentId, limit, minSimilarity]);

  return (
    result.rows as Array<{
      id: string | number;
      content: string;
      similarity: string | number;
      distance: string | number;
      metadata?: Record<string, unknown>;
    }>
  ).map((row) => ({
    id: row.id,
    content: row.content,
    similarity: typeof row.similarity === 'string' ? parseFloat(row.similarity) : row.similarity,
    distance: typeof row.distance === 'string' ? parseFloat(row.distance) : row.distance,
    metadata: row.metadata,
  }));
}

/** Calculate cosine similarity between two vectors */
export function cosineSimilarity(a: number[], b: number[]): number {
  if (a.length !== b.length) {
    throw new Error('Vectors must have the same length');
  }

  let dotProduct = 0;
  let normA = 0;
  let normB = 0;

  for (let i = 0; i < a.length; i++) {
    dotProduct += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }

  const denominator = Math.sqrt(normA) * Math.sqrt(normB);
  if (denominator === 0) return 0;

  return dotProduct / denominator;
}
