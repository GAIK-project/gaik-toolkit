import { beforeEach, describe, expect, it } from 'vitest';
import { EmbeddingCache, createCachedBatchEmbedder, createCachedEmbedder } from '../src/embeddings/cache.js';

describe('EmbeddingCache', () => {
  let cache: EmbeddingCache;

  beforeEach(() => {
    cache = new EmbeddingCache(100);
  });

  it('should store and retrieve embeddings', () => {
    const embedding = [0.1, 0.2, 0.3, 0.4];
    cache.set('hello', embedding);
    expect(cache.get('hello')).toEqual(embedding);
  });

  it('should return undefined for missing keys', () => {
    expect(cache.get('nonexistent')).toBeUndefined();
  });

  it('should track cache statistics', () => {
    cache.set('key1', [0.1, 0.2]);
    cache.get('key1');
    cache.get('key2');

    const stats = cache.getStats();
    expect(stats.hits).toBe(1);
    expect(stats.misses).toBe(1);
    expect(stats.hitRate).toBe(0.5);
  });

  it('should evict oldest entries when at capacity', () => {
    const smallCache = new EmbeddingCache(3);
    smallCache.set('a', [1]);
    smallCache.set('b', [2]);
    smallCache.set('c', [3]);
    smallCache.set('d', [4]);

    expect(smallCache.get('a')).toBeUndefined();
    expect(smallCache.get('b')).toEqual([2]);
  });

  it('should update LRU order on access', () => {
    const smallCache = new EmbeddingCache(3);
    smallCache.set('a', [1]);
    smallCache.set('b', [2]);
    smallCache.set('c', [3]);
    smallCache.get('a');
    smallCache.set('d', [4]);

    expect(smallCache.get('a')).toEqual([1]);
    expect(smallCache.get('b')).toBeUndefined();
  });

  it('should clear all entries', () => {
    cache.set('a', [1]);
    cache.set('b', [2]);
    cache.clear();

    expect(cache.size).toBe(0);
    expect(cache.get('a')).toBeUndefined();
  });
});

describe('createCachedEmbedder', () => {
  it('should cache embedding results', async () => {
    let callCount = 0;
    const mockEmbedFn = async (text: string) => {
      callCount++;
      return text.split('').map((c) => c.charCodeAt(0));
    };

    const cache = new EmbeddingCache();
    const cachedEmbed = createCachedEmbedder(mockEmbedFn, cache);

    await cachedEmbed('hello');
    expect(callCount).toBe(1);

    await cachedEmbed('hello');
    expect(callCount).toBe(1);

    await cachedEmbed('world');
    expect(callCount).toBe(2);
  });
});

describe('createCachedBatchEmbedder', () => {
  it('should only embed uncached texts', async () => {
    let embedCalls: string[][] = [];
    const mockBatchFn = async (texts: string[]) => {
      embedCalls.push(texts);
      return texts.map((t) => t.split('').map((c) => c.charCodeAt(0)));
    };

    const cache = new EmbeddingCache();
    const cachedBatch = createCachedBatchEmbedder(mockBatchFn, cache);

    await cachedBatch(['a', 'b', 'c']);
    expect(embedCalls[0]).toEqual(['a', 'b', 'c']);

    embedCalls = [];
    await cachedBatch(['a', 'd', 'e']);
    expect(embedCalls[0]).toEqual(['d', 'e']);

    embedCalls = [];
    await cachedBatch(['a', 'b']);
    expect(embedCalls.length).toBe(0);
  });
});
