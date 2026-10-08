# searching-documents

An [Agent Skill](https://agentskills.io/specification) that helps a coding agent build and
debug document search with the [`gaik`](https://pypi.org/project/gaik/) toolkit: hybrid search
that combines pgvector similarity with Postgres full-text search.

## Use it when

- you add semantic or hybrid search over document chunks, or build RAG retrieval with gaik;
- you index Finnish text for full-text search;
- you need to decide whether a search found anything relevant at all;
- search misbehaves without an error: no keyword hits, a word in the text is not found, or
  hybrid returns the same results as vector-only;
- you measure retrieval with Hit@K or MRR, or judge whether a reranker helped.

Example request:

```text
Use the searching-documents skill to add hybrid search over my document chunks and measure it
with Hit@K.
```

## What it covers

- The gaik recipe: embedding, storing, and semantic, keyword and hybrid search.
- Three ways the keyword side returns nothing without an error.
- Finnish and other inflected languages.
- Why a result count is not evidence, and how to set a relevance floor.
- Going from chunks to documents, measuring retrieval, and rerankers.

## Files

| File | Content |
|---|---|
| `SKILL.md` | The workflow the agent follows |
| `references/finnish.md` | Rules for Finnish text, read before indexing Finnish |
| `references/evaluating-retrieval.md` | How to measure retrieval, read before reporting a number |
| `references/postgres-without-gaik.md` | The same design in plain SQL, for an existing schema or a TypeScript app |

## Needs

Postgres with pgvector, `pip install "gaik[pg-vector-store,embedder,ranker]"`, and
`gaik[finnish-rag]` for Finnish. Embeddings need a provider key.

Install the skill with the [gaik-toolkit plugin](../../README.md#installing).
