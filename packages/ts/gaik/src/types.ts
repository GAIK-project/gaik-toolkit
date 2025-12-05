/**
 * Re-exports all types from @gaik
 */

// Config
export type { AzureConfig, OpenAIConfig } from './config/env.js';

// Embeddings
export type { EmbeddingCacheStats, EmbeddingProvider } from './embeddings/types.js';

// Generation
export type {
  GenerateFromMessagesOptions,
  GenerateObjectOptions,
  GenerateObjectResult,
  GenerateTextOptions,
  GenerateTextResult,
  Message,
  StreamFromMessagesOptions,
  StreamResult,
  StreamTextOptions,
  TokenUsage,
} from './generation/types.js';

// Prompts
export type { RenderedPrompt } from './prompts/types.js';

// Search
export type {
  HybridSearchOptions,
  HybridSearchResult,
  PoolLike,
  SemanticSearchOptions,
  VectorSearchResult,
} from './search/types.js';
