import { generateText, type LanguageModel } from 'ai';
import type { GenerateFromMessagesOptions, GenerateTextOptions, GenerateTextResult } from './types.js';

/** Generate text using an AI model */
export async function generate(options: GenerateTextOptions): Promise<GenerateTextResult> {
  const { model, prompt, system, maxTokens, temperature, stopSequences } = options;

  const result = await generateText({
    model,
    prompt,
    ...(system && { system }),
    ...(maxTokens !== undefined && { maxTokens }),
    ...(temperature !== undefined && { temperature }),
    ...(stopSequences && { stopSequences }),
  });

  return {
    text: result.text,
    usage: {
      promptTokens: result.usage?.promptTokens ?? 0,
      completionTokens: result.usage?.completionTokens ?? 0,
      totalTokens: result.usage?.totalTokens ?? 0,
    },
    finishReason: result.finishReason ?? 'unknown',
  };
}

/** Generate text from conversation history */
export async function generateFromMessages(
  options: GenerateFromMessagesOptions
): Promise<GenerateTextResult> {
  const { model, messages, maxTokens, temperature } = options;

  const result = await generateText({
    model,
    messages,
    ...(maxTokens !== undefined && { maxTokens }),
    ...(temperature !== undefined && { temperature }),
  });

  return {
    text: result.text,
    usage: {
      promptTokens: result.usage?.promptTokens ?? 0,
      completionTokens: result.usage?.completionTokens ?? 0,
      totalTokens: result.usage?.totalTokens ?? 0,
    },
    finishReason: result.finishReason ?? 'unknown',
  };
}

/** Simple text completion helper */
export async function complete(model: LanguageModel, prompt: string, system?: string): Promise<string> {
  const result = await generate({ model, prompt, system });
  return result.text;
}
