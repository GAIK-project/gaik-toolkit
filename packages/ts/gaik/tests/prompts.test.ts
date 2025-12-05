import { describe, expect, it } from 'vitest';
import { parsePromptFile, renderPrompt } from '../src/prompts/index.js';

describe('renderPrompt', () => {
  it('should substitute variables', () => {
    const template = 'Hello {{name}}, welcome to {{place}}!';
    const result = renderPrompt(template, { name: 'John', place: 'Finland' });
    expect(result).toBe('Hello John, welcome to Finland!');
  });

  it('should handle missing variables', () => {
    const template = 'Hello {{name}}!';
    const result = renderPrompt(template, {});
    expect(result).toBe('Hello !');
  });

  it('should handle templates without variables', () => {
    const template = 'Static text';
    const result = renderPrompt(template, { unused: 'value' });
    expect(result).toBe('Static text');
  });
});

describe('parsePromptFile', () => {
  it('should parse system and prompt sections', () => {
    const content = `You are a helpful assistant.
---
Do this task: {{task}}`;

    const result = parsePromptFile(content);
    expect(result.system).toBe('You are a helpful assistant.');
    expect(result.prompt).toBe('Do this task: {{task}}');
  });

  it('should handle content without separator', () => {
    const content = 'Just a prompt';
    const result = parsePromptFile(content);
    expect(result.system).toBeUndefined();
    expect(result.prompt).toBe('Just a prompt');
  });

  it('should handle multiple sections', () => {
    const content = `System message
---
First prompt section
---
Second prompt section`;

    const result = parsePromptFile(content);
    expect(result.system).toBe('System message');
    expect(result.prompt).toContain('First prompt section');
  });
});

