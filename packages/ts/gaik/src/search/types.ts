export interface VectorSearchResult {
  id: string | number;
  content: string;
  similarity: number;
  distance: number;
  metadata?: Record<string, unknown>;
}

export interface HybridSearchResult {
  id: string | number;
  content: string;
  semanticRank: number | null;
  keywordRank: number | null;
  rrfScore: number;
  metadata?: Record<string, unknown>;
}

export interface SemanticSearchOptions {
  tableName: string;
  queryEmbedding: number[];
  limit?: number;
  minSimilarity?: number;
}

export interface HybridSearchOptions {
  tableName: string;
  queryText?: string;
  queryEmbedding?: number[];
  limit?: number;
  semanticWeight?: number;
  keywordWeight?: number;
  rrfK?: number;
}

export interface PoolLike {
  query(text: string, values?: unknown[]): Promise<{ rows: unknown[]; rowCount: number | null }>;
}
