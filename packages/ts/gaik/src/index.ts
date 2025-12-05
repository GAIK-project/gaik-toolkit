/**
 * GAIK AI Toolkit - Simplified AI utilities built on Vercel AI SDK
 *
 * @example
 * ```typescript
 * import { openai } from '@ai-sdk/openai';
 * import { generate, embedText } from '@gaik';
 *
 * const result = await generate({
 *   model: openai('gpt-4.1'),
 *   prompt: 'Hello!',
 * });
 *
 * const vector = await embedText('Hello', openai.textEmbeddingModel('text-embedding-3-small'));
 * ```
 */

// Types
export type {
    AzureConfig,
    EmbeddingCacheStats,
    EmbeddingProvider,
    GenerateFromMessagesOptions,
    GenerateObjectOptions,
    GenerateObjectResult,
    GenerateTextOptions,
    GenerateTextResult,
    HybridSearchOptions,
    HybridSearchResult,
    Message,
    OpenAIConfig,
    PoolLike,
    RenderedPrompt,
    SemanticSearchOptions,
    StreamFromMessagesOptions,
    StreamResult,
    StreamTextOptions,
    TokenUsage,
    VectorSearchResult
} from './types.js';

// Config
export {
    getAzureConfig,
    getOpenAIConfig,
    requireAzureConfig,
    requireOpenAIConfig,
    validateEnv
} from './config/index.js';

// Embeddings
export {
    clearGlobalEmbeddingCache,
    createCachedBatchEmbedder,
    createCachedEmbedder,
    createEmbeddingProvider,
    EmbeddingCache,
    embedText,
    embedTexts,
    getGlobalEmbeddingCache
} from './embeddings/index.js';

// Generation
export {
    collectStream,
    complete,
    extract,
    generate,
    generateFromMessages,
    generateList,
    generateStream,
    generateStructured,
    printStream,
    streamFromMessages,
    z
} from './generation/index.js';

export type { TextStreamPart } from 'ai';

// Prompts
export { parsePromptFile, renderPrompt } from './prompts/index.js';

// Search
export {
    cosineSimilarity,
    findSimilar,
    hybridSearch,
    keywordSearch,
    reciprocalRankFusion,
    rerank,
    semanticOnlySearch,
    semanticSearch,
    semanticSearchCustom
} from './search/index.js';

// SQL
export {
    ALL_MIGRATIONS_SQL,
    EXAMPLE_TABLE_SQL,
    EXTENSIONS_SQL,
    HYBRID_SEARCH_SQL
} from './sql/index.js';

export const VERSION = '0.1.0';
