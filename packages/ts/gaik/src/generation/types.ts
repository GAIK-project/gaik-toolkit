import type { LanguageModel } from 'ai';
import type { z } from 'zod';

export interface TokenUsage {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

export interface Message {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface GenerateTextOptions {
  model: LanguageModel;
  prompt: string;
  system?: string;
  maxTokens?: number;
  temperature?: number;
  stopSequences?: string[];
}

export interface GenerateTextResult {
  text: string;
  usage: TokenUsage;
  finishReason: string;
}

export interface GenerateFromMessagesOptions {
  model: LanguageModel;
  messages: Message[];
  maxTokens?: number;
  temperature?: number;
}

export interface GenerateObjectOptions<T extends z.ZodType> {
  model: LanguageModel;
  schema: T;
  prompt: string;
  system?: string;
  temperature?: number;
  maxTokens?: number;
}

export interface GenerateObjectResult<T> {
  object: T;
  usage: TokenUsage;
}

export interface StreamTextOptions {
  model: LanguageModel;
  prompt: string;
  system?: string;
  maxTokens?: number;
  temperature?: number;
  onChunk?: (chunk: string) => void;
  onComplete?: (text: string) => void;
  onError?: (error: Error) => void;
}

export interface StreamResult {
  textStream: AsyncIterable<string>;
  text: Promise<string>;
  usage: Promise<TokenUsage>;
}

export interface StreamFromMessagesOptions {
  model: LanguageModel;
  messages: Message[];
  maxTokens?: number;
  temperature?: number;
}
