# PostgreSQL Vector Store

PostgreSQL-backed vector store with semantic, keyword, and hybrid search using
[pgvector](https://github.com/pgvector/pgvector).

## Installation

```bash
pip install gaik[pg-vector-store]
```

You also need a PostgreSQL instance with the **pgvector** extension:

```bash
docker run -d --name pgvector-db \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=mydb \
  -p 5432:5432 \
  pgvector/pgvector:pg17
```

## Quick Start

```python
from langchain_core.documents import Document
from gaik.software_components.RAG.pg_vector_store import PgVectorStore

with PgVectorStore("postgresql://postgres:postgres@localhost:5432/mydb") as store:
    # Create table, indexes, and search functions (idempotent)
    store.setup()

    # Insert documents with embeddings
    docs = [Document(page_content="Hello world", metadata={"source": "demo"})]
    embeddings = [[0.1, 0.2, ...]]  # from your embedding model
    ids = store.add(docs, embeddings)

    # Semantic search (pure vector similarity)
    results = store.search_semantic(query_embedding, top_k=5)

    # Keyword search (PostgreSQL full-text search)
    results = store.search_keyword("hello", top_k=5)

    # Hybrid search (vector + FTS combined with RRF)
    results = store.search_hybrid(query_embedding, "hello", top_k=5)
```

## Features

- **Semantic search** -- cosine similarity via pgvector HNSW index
- **Keyword search** -- PostgreSQL full-text search (tsvector/tsquery)
- **Hybrid search (RRF)** -- Reciprocal Rank Fusion combining both methods
- **Weighted hybrid search** -- linear combination with configurable weights
- **JSONB metadata filtering** on all search methods
- **VectorStore compatibility** -- `search()` method works with existing `Retriever`
- **Context manager** -- automatic connection cleanup

## API

### Constructor

```python
PgVectorStore(
    connection_string: str,
    *,
    table_name: str = "documents",
    embedding_dim: int = 1536,
    fts_language: str = "simple",
)
```

### Methods

| Method | Description |
|--------|-------------|
| `setup()` | Create extensions, table, indexes, SQL functions |
| `add(documents, embeddings)` | Insert documents, returns list of IDs |
| `count()` | Total document count |
| `delete(document_ids)` | Delete by ID, returns deleted count |
| `search(query_embedding, *, top_k, filters)` | VectorStore-compatible semantic search |
| `search_semantic(query_embedding, *, top_k, threshold, filters)` | Pure vector search |
| `search_keyword(query_text, *, top_k, filters)` | Pure FTS keyword search |
| `search_hybrid(query_embedding, query_text, *, top_k, rrf_k, semantic_weight, keyword_weight, filters)` | RRF hybrid search |
| `search_hybrid_weighted(query_embedding, query_text, *, top_k, semantic_weight, keyword_weight, filters)` | Weighted hybrid search |
| `close()` | Close database connection |

### Return Type

All search methods return `list[tuple[Document, float]]` -- a list of
(Document, score) pairs sorted by score descending.

## Configuration

### Connection String

Standard PostgreSQL URI: `postgresql://user:password@host:port/database`

### FTS Language

The `fts_language` parameter controls PostgreSQL text search stemming:

- `"simple"` -- no stemming (default, good for mixed/multilingual content)
- `"english"` -- English stemmer
- `"finnish"` -- Finnish stemmer
- See [PostgreSQL docs](https://www.postgresql.org/docs/current/textsearch-configuration.html) for all options

### Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string (use in your app) |
| `AZURE_API_KEY` | For embedding generation with Azure OpenAI |
| `AZURE_ENDPOINT` | Azure OpenAI endpoint |

## Examples

See [pg_vector_store_example.py](../../../../examples/software_components/RAG/pg_vector_store_example.py)
for a complete working example.
