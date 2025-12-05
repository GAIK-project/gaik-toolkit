/**
 * Embeddings module - Generate and cache text embeddings
 */

export type { EmbeddingCacheStats, EmbeddingProvider } from './types.js';

export { createEmbeddingProvider, embedText, embedTexts } from './provider.js';

export {
    EmbeddingCache, clearGlobalEmbeddingCache,
    createCachedBatchEmbedder,
    createCachedEmbedder, getGlobalEmbeddingCache
} from './cache.js';

