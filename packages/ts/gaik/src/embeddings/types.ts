/** Embedding provider interface */
export interface EmbeddingProvider {
  embedBatch: (texts: string[]) => Promise<number[][]>;
  embedOne: (text: string) => Promise<number[]>;
}

/** Cache statistics */
export interface EmbeddingCacheStats {
  size: number;
  maxSize: number;
  hits: number;
  misses: number;
  hitRate: number;
}
