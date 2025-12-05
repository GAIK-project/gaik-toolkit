import { generateObject, type LanguageModel } from 'ai';
import { z } from 'zod';
import type { GenerateObjectOptions, GenerateObjectResult } from './types.js';

/** Generate a structured object using Zod schema */
export async function generateStructured<T extends z.ZodType>(
  options: GenerateObjectOptions<T>
): Promise<GenerateObjectResult<z.infer<T>>> {
  const { model, schema, prompt, system, temperature, maxTokens } = options;

  const result = await generateObject({
    model,
    schema,
    prompt,
    ...(system && { system }),
    ...(temperature !== undefined && { temperature }),
    ...(maxTokens !== undefined && { maxTokens }),
  });

  return {
    object: result.object,
    usage: {
      promptTokens: result.usage?.promptTokens ?? 0,
      completionTokens: result.usage?.completionTokens ?? 0,
      totalTokens: result.usage?.totalTokens ?? 0,
    },
  };
}

/** Extract structured data from text */
export async function extract<T extends z.ZodType>(
  model: LanguageModel,
  schema: T,
  text: string,
  instructions?: string
): Promise<z.infer<T>> {
  const prompt = instructions ? `${instructions}\n\nText:\n${text}` : `Extract information from:\n${text}`;

  const result = await generateStructured({
    model,
    schema,
    prompt,
    system: 'You are a precise data extraction assistant. Extract only the information present in the text.',
  });

  return result.object;
}

/** Generate a list of items matching a schema */
export async function generateList<T extends z.ZodType>(
  model: LanguageModel,
  itemSchema: T,
  prompt: string
): Promise<z.infer<T>[]> {
  const result = await generateStructured({
    model,
    schema: z.array(itemSchema),
    prompt,
  });

  return result.object;
}

export { z } from 'zod';

