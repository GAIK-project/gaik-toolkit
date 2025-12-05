import { streamText, type TextStreamPart } from 'ai';
import type { StreamFromMessagesOptions, StreamResult, StreamTextOptions } from './types.js';

/** Stream text generation from an AI model */
export async function generateStream(options: StreamTextOptions): Promise<StreamResult> {
  const { model, prompt, system, maxTokens, temperature, onChunk, onComplete, onError } = options;

  const result = streamText({
    model,
    prompt,
    ...(system && { system }),
    ...(maxTokens !== undefined && { maxTokens }),
    ...(temperature !== undefined && { temperature }),
  });

  const wrappedTextStream = (async function* () {
    let fullText = '';
    try {
      for await (const chunk of result.textStream) {
        fullText += chunk;
        onChunk?.(chunk);
        yield chunk;
      }
      onComplete?.(fullText);
    } catch (error) {
      onError?.(error as Error);
      throw error;
    }
  })();

  return {
    textStream: wrappedTextStream,
    text: result.text,
    usage: result.usage.then((u) => ({
      promptTokens: u?.promptTokens ?? 0,
      completionTokens: u?.completionTokens ?? 0,
      totalTokens: u?.totalTokens ?? 0,
    })),
  };
}

/** Stream text from conversation history */
export async function streamFromMessages(options: StreamFromMessagesOptions): Promise<StreamResult> {
  const { model, messages, maxTokens, temperature } = options;

  const result = streamText({
    model,
    messages,
    ...(maxTokens !== undefined && { maxTokens }),
    ...(temperature !== undefined && { temperature }),
  });

  return {
    textStream: result.textStream,
    text: result.text,
    usage: result.usage.then((u) => ({
      promptTokens: u?.promptTokens ?? 0,
      completionTokens: u?.completionTokens ?? 0,
      totalTokens: u?.totalTokens ?? 0,
    })),
  };
}

/** Collect all chunks from a stream into a string */
export async function collectStream(stream: AsyncIterable<string>): Promise<string> {
  let result = '';
  for await (const chunk of stream) {
    result += chunk;
  }
  return result;
}

/** Print stream to stdout */
export async function printStream(stream: AsyncIterable<string>): Promise<void> {
  for await (const chunk of stream) {
    process.stdout.write(chunk);
  }
  process.stdout.write('\n');
}

export type { TextStreamPart };
