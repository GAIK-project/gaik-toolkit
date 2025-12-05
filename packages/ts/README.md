# TypeScript Packages

This folder contains TypeScript/JavaScript npm packages for the GAIK toolkit.

## Available Packages

### [@gaik/ai](./gaik/)

AI toolkit providing:

- Provider-agnostic AI operations (Azure OpenAI, OpenAI via Vercel AI SDK)
- Embedding generation and caching
- Structured text generation with Zod schemas
- PostgreSQL vector search (semantic & hybrid)
- RAG pipeline utilities
- Prompt template management

```bash
cd packages/ts/gaik
pnpm install
pnpm run build
pnpm test
```

> **Note:** You can also use `npm` instead of `pnpm` if preferred.

## Package Structure

| Folder                                    | Purpose                           |
| ----------------------------------------- | --------------------------------- |
| `packages/ts/<package-name>/src/`         | Package source code               |
| `packages/ts/<package-name>/tests/`       | Co-located unit/integration tests |
| `packages/ts/<package-name>/package.json` | Package metadata + scripts        |

## Creating a New TypeScript Package

1. **Scaffold**

   ```bash
   mkdir -p packages/ts/<package-name>/{src,tests}
   cd packages/ts/<package-name>
   pnpm init
   ```

2. **Tooling**

   - Prefer TypeScript (`tsconfig.json`) and ESLint/Prettier configs stored inside the package directory.
   - Keep tests next to the feature they cover (e.g., `src/parser/tests/`).

3. **CI**

   - Expose a `test` script in `package.json`.
   - Future workflows can iterate over `packages/ts/*` similar to the Python runner.

4. **Docs**
   - Add a `README.md` inside the package describing usage and build/test commands.
