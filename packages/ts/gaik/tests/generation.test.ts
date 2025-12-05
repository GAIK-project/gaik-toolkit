import { describe, it, expect } from 'vitest';
import { z } from 'zod';

describe('Zod Schema Integration', () => {
  it('should create valid extraction schemas', () => {
    const PersonSchema = z.object({
      name: z.string(),
      age: z.number(),
      email: z.string().email().optional(),
    });

    const result = PersonSchema.safeParse({
      name: 'John Doe',
      age: 30,
      email: 'john@example.com',
    });

    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.name).toBe('John Doe');
    }
  });

  it('should validate nested schemas', () => {
    const CompanySchema = z.object({
      name: z.string(),
      address: z.object({
        street: z.string(),
        city: z.string(),
      }),
    });

    const result = CompanySchema.safeParse({
      name: 'GAIK Corp',
      address: { street: '123 AI Street', city: 'Helsinki' },
    });

    expect(result.success).toBe(true);
  });

  it('should handle arrays in schemas', () => {
    const TaskSchema = z.object({
      title: z.string(),
      priority: z.enum(['low', 'medium', 'high']),
      completed: z.boolean().default(false),
    });

    const result = z.array(TaskSchema).safeParse([
      { title: 'Task 1', priority: 'high' },
      { title: 'Task 2', priority: 'low', completed: true },
    ]);

    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data[0].completed).toBe(false);
    }
  });

  it('should reject invalid data', () => {
    const StrictSchema = z.object({
      required: z.string(),
      number: z.number().positive(),
    });

    const result = StrictSchema.safeParse({
      required: 'present',
      number: -5,
    });

    expect(result.success).toBe(false);
  });
});
