import { embed, embedMany, type EmbeddingModel } from 'ai';
import type { EmbeddingProvider } from './types.js';

/** Create an embedding provider from a Vercel AI SDK embedding model */
export function createEmbeddingProvider(
  model: EmbeddingModel<string>,
  options: { maxBatchSize?: number } = {}
): EmbeddingProvider {
  const { maxBatchSize = 100 } = options;

  return {
    async embedBatch(texts: string[]): Promise<number[][]> {
      if (texts.length === 0) return [];

      if (texts.length <= maxBatchSize) {
        const result = await embedMany({ model, values: texts });
        return result.embeddings;
      }

      const batches: string[][] = [];
      for (let i = 0; i < texts.length; i += maxBatchSize) {
        batches.push(texts.slice(i, i + maxBatchSize));
      }

      const allEmbeddings: number[][] = [];
      for (const batch of batches) {
        const result = await embedMany({ model, values: batch });
        allEmbeddings.push(...result.embeddings);
      }

      return allEmbeddings;
    },

    async embedOne(text: string): Promise<number[]> {
      const result = await embed({ model, value: text });
      return result.embedding;
    },
  };
}

/** Embed a single text */
export async function embedText(text: string, model: EmbeddingModel<string>): Promise<number[]> {
  const result = await embed({ model, value: text });
  return result.embedding;
}

/** Embed multiple texts */
export async function embedTexts(texts: string[], model: EmbeddingModel<string>): Promise<number[][]> {
  if (texts.length === 0) return [];
  const result = await embedMany({ model, values: texts });
  return result.embeddings;
}
