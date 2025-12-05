import type { EmbeddingCacheStats } from './types.js';

/** LRU cache for embeddings */
export class EmbeddingCache {
  private cache: Map<string, number[]>;
  private maxSize: number;
  private hits = 0;
  private misses = 0;

  constructor(maxSize = 10000) {
    this.cache = new Map();
    this.maxSize = maxSize;
  }

  private generateKey(text: string): string {
    let hash = 0;
    for (let i = 0; i < text.length; i++) {
      const char = text.charCodeAt(i);
      hash = (hash << 5) - hash + char;
      hash = hash & hash;
    }
    return `${hash}_${text.length}`;
  }

  get(text: string): number[] | undefined {
    const key = this.generateKey(text);
    const value = this.cache.get(key);

    if (value !== undefined) {
      this.hits++;
      this.cache.delete(key);
      this.cache.set(key, value);
      return value;
    }

    this.misses++;
    return undefined;
  }

  set(text: string, embedding: number[]): void {
    const key = this.generateKey(text);

    if (this.cache.has(key)) {
      this.cache.delete(key);
    }

    while (this.cache.size >= this.maxSize) {
      const firstKey = this.cache.keys().next().value;
      if (firstKey !== undefined) {
        this.cache.delete(firstKey);
      }
    }

    this.cache.set(key, embedding);
  }

  has(text: string): boolean {
    return this.cache.has(this.generateKey(text));
  }

  clear(): void {
    this.cache.clear();
    this.hits = 0;
    this.misses = 0;
  }

  getStats(): EmbeddingCacheStats {
    const total = this.hits + this.misses;
    return {
      size: this.cache.size,
      maxSize: this.maxSize,
      hits: this.hits,
      misses: this.misses,
      hitRate: total > 0 ? this.hits / total : 0,
    };
  }

  get size(): number {
    return this.cache.size;
  }
}

let globalCache: EmbeddingCache | null = null;

export function getGlobalEmbeddingCache(maxSize?: number): EmbeddingCache {
  if (!globalCache) {
    globalCache = new EmbeddingCache(maxSize);
  }
  return globalCache;
}

export function clearGlobalEmbeddingCache(): void {
  if (globalCache) {
    globalCache.clear();
  }
  globalCache = null;
}

/** Create a cached embedding function */
export function createCachedEmbedder(
  embedFn: (text: string) => Promise<number[]>,
  cache?: EmbeddingCache
): (text: string) => Promise<number[]> {
  const embeddingCache = cache ?? getGlobalEmbeddingCache();

  return async (text: string): Promise<number[]> => {
    const cached = embeddingCache.get(text);
    if (cached !== undefined) return cached;

    const embedding = await embedFn(text);
    embeddingCache.set(text, embedding);
    return embedding;
  };
}

/** Create a cached batch embedding function */
export function createCachedBatchEmbedder(
  embedBatchFn: (texts: string[]) => Promise<number[][]>,
  cache?: EmbeddingCache
): (texts: string[]) => Promise<number[][]> {
  const embeddingCache = cache ?? getGlobalEmbeddingCache();

  return async (texts: string[]): Promise<number[][]> => {
    const results: (number[] | null)[] = new Array(texts.length).fill(null);
    const uncachedIndices: number[] = [];
    const uncachedTexts: string[] = [];

    for (let i = 0; i < texts.length; i++) {
      const cached = embeddingCache.get(texts[i]);
      if (cached !== undefined) {
        results[i] = cached;
      } else {
        uncachedIndices.push(i);
        uncachedTexts.push(texts[i]);
      }
    }

    if (uncachedTexts.length > 0) {
      const newEmbeddings = await embedBatchFn(uncachedTexts);
      for (let i = 0; i < uncachedTexts.length; i++) {
        embeddingCache.set(uncachedTexts[i], newEmbeddings[i]);
        results[uncachedIndices[i]] = newEmbeddings[i];
      }
    }

    return results as number[][];
  };
}
