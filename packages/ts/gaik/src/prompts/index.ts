/**
 * Prompts module - Simple prompt utilities
 */

export type { RenderedPrompt } from './types.js';

/** Render a prompt template with variables ({{var}} syntax) */
export function renderPrompt(template: string, variables: Record<string, string> = {}): string {
  return template.replace(/\{\{(\w+)\}\}/g, (_, key) => variables[key] ?? '');
}

/** Parse a markdown file into system/prompt sections */
export function parsePromptFile(content: string): { system?: string; prompt: string } {
  const parts = content.split(/^---$/m).map((s) => s.trim()).filter(Boolean);

  if (parts.length >= 2) {
    return { system: parts[0], prompt: parts.slice(1).join('\n\n') };
  }

  return { prompt: parts[0] || content };
}
