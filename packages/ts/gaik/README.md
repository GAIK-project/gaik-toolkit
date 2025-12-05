# @gaik

GAIK AI Toolkit - Simplified AI utilities built on [Vercel AI SDK](https://sdk.vercel.ai/).

## Features

- **Embeddings**: Generate and cache text embeddings
- **Generation**: Text and structured object generation with Zod schemas
- **Streaming**: Real-time text streaming
- **Prompts**: Simple prompt utilities with variable substitution
- **Search**: SQL functions for semantic and hybrid search (PostgreSQL/pgvector)

## Philosophy

Thin wrapper around Vercel AI SDK. **You bring the model, we provide utilities.**

- Models are passed as parameters from `@ai-sdk/openai`, `@ai-sdk/azure`, etc.
- No database client - use your own (`pg`, Prisma, Drizzle, etc.)
- Just utilities that make AI development easier

## Installation

```bash
npm install @gaik ai @ai-sdk/openai
```

## Quick Start

### Text Generation

```typescript
import { openai } from '@ai-sdk/openai';
import { generate, complete } from '@gaik';

const result = await generate({
  model: openai('gpt-4.1'),
  prompt: 'Explain knowledge management.',
  system: 'You are a business consultant.',
});
console.log(result.text);

// Simple helper
const text = await complete(openai('gpt-4.1'), 'Hello!');
```

### Structured Data Extraction

```typescript
import { openai } from '@ai-sdk/openai';
import { extract, z } from '@gaik';

const PersonSchema = z.object({
  name: z.string(),
  age: z.number(),
  email: z.string().email().optional(),
});

const person = await extract(
  openai('gpt-4.1'),
  PersonSchema,
  'John Doe is 35 years old, email john@example.com'
);
// { name: 'John Doe', age: 35, email: 'john@example.com' }
```

### Embeddings

```typescript
import { openai } from '@ai-sdk/openai';
import { embedText, embedTexts, createEmbeddingProvider } from '@gaik';

const vector = await embedText(
  'Hello, world!',
  openai.textEmbeddingModel('text-embedding-3-small')
);

const vectors = await embedTexts(
  ['Hello', 'World'],
  openai.textEmbeddingModel('text-embedding-3-small')
);

// Reusable provider
const embedder = createEmbeddingProvider(
  openai.textEmbeddingModel('text-embedding-3-small')
);
const v1 = await embedder.embedOne('text');
const vN = await embedder.embedBatch(['a', 'b', 'c']);
```

### Vector Search (PostgreSQL)

```typescript
import { Pool } from 'pg';
import { openai } from '@ai-sdk/openai';
import { hybridSearch, semanticSearch, embedText, EXTENSIONS_SQL, HYBRID_SEARCH_SQL } from '@gaik';

const pool = new Pool({ connectionString: process.env.DATABASE_URL });
await pool.query(EXTENSIONS_SQL);
await pool.query(HYBRID_SEARCH_SQL);

const embedding = await embedText(
  'machine learning applications',
  openai.textEmbeddingModel('text-embedding-3-small')
);

// Hybrid search (semantic + keyword)
const results = await hybridSearch(pool, {
  tableName: 'documents',
  queryText: 'machine learning',
  queryEmbedding: embedding,
  semanticWeight: 0.7,
  keywordWeight: 0.3,
});

// Semantic-only search
const semanticResults = await semanticSearch(pool, {
  tableName: 'documents',
  queryEmbedding: embedding,
  limit: 10,
  minSimilarity: 0.7,
});
```

### Prompts

Use `.md` files as prompt templates with variable substitution:

```typescript
import { renderPrompt, parsePromptFile } from '@gaik';
import { readFileSync } from 'fs';

// prompts/summarize.md:
// You are a professional summarizer.
// ---
// Summarize the following text in {{style}} style:
// 
// {{text}}

const content = readFileSync('prompts/summarize.md', 'utf-8');
const { system, prompt } = parsePromptFile(content);

const rendered = renderPrompt(prompt, {
  style: 'concise',
  text: 'Long document...',
});
```

## API Reference

### Embeddings

- `embedText(text, model)` - Embed single text
- `embedTexts(texts, model)` - Embed multiple texts  
- `createEmbeddingProvider(model)` - Create reusable provider
- `EmbeddingCache` - LRU cache for embeddings

### Generation

- `generate(options)` - Generate text with full options
- `complete(model, prompt)` - Simple completion
- `generateStructured(options)` - Generate with Zod schema
- `extract(model, schema, text)` - Extract structured data
- `generateList(model, schema, prompt)` - Generate list of items
- `generateStream(options)` - Stream text generation

### Search

- `semanticSearch(pool, options)` - Vector similarity search
- `hybridSearch(pool, options)` - Combined semantic + keyword
- `cosineSimilarity(a, b)` - Calculate vector similarity
- `reciprocalRankFusion(lists, k)` - Combine ranked lists

### SQL

- `EXTENSIONS_SQL` - SQL for pgvector/pg_trgm extensions
- `HYBRID_SEARCH_SQL` - SQL for search functions
- `EXAMPLE_TABLE_SQL` - Example table structure

### Prompts

- `renderPrompt(template, variables)` - Render template with variables
- `parsePromptFile(content)` - Parse markdown file into system/prompt

## Using with Different Providers

```typescript
// OpenAI (default: gpt-4.1)
import { openai } from '@ai-sdk/openai';
const result = await generate({
  model: openai('gpt-4.1'),
  prompt: 'Hello',
});

// Azure OpenAI
import { azure } from '@ai-sdk/azure';
const result = await generate({
  model: azure('my-gpt4-deployment'),
  prompt: 'Hello',
});

// Anthropic
import { anthropic } from '@ai-sdk/anthropic';
const result = await generate({
  model: anthropic('claude-sonnet-4-20250514'),
  prompt: 'Hello',
});
```

## License

MIT
