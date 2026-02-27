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

---

## Video Search SQL Reference

The `sql/` subfolder contains production-tested SQL migrations for building a
**semantic video search** system with pgvector. These scripts come from the
[semantic-video-search](https://github.com/GAIK-project/QAdental) project and
implement hybrid search over video subtitle segments.

### Prerequisites

- PostgreSQL 17 with extensions: **pgvector**, **pg_trgm**, **unaccent**
- Embeddings from an OpenAI-compatible model (default: `text-embedding-3-small`, 1536 dimensions)

```bash
docker run -d --name pgvector-db \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=videosearch \
  -p 5432:5432 \
  pgvector/pgvector:pg17
```

### Schema Overview

| Table                 | Purpose                                                       |
| --------------------- | ------------------------------------------------------------- |
| `s3_videos` | Video metadata (S3 keys, status, duration, JSONB metadata) |
| `s3_segments` | Subtitle segments (~30-60s) with `vector(1536)` embeddings |
| `s3_subtitle_cues` | Individual subtitle lines (~2-5s) for precise timestamp seeking |

### Migration Files

Run in order — each migration is idempotent (`IF NOT EXISTS` / `CREATE OR REPLACE`):

| File                               | Description                                                                      |
| ---------------------------------- | -------------------------------------------------------------------------------- |
| `0000_initial_schema.sql` | Base tables (`s3_videos`, `s3_segments`), HNSW vector index, status/date indexes |
| `0001_add_fulltext_search.sql` | Auto-generated `tsvector` column, GIN index, `hybrid_search()` function with RRF |
| `0002_add_subtitle_cues.sql` | `s3_subtitle_cues` table for precise seek within segments |
| `0003_add_trigram_search.sql` | `pg_trgm` + `unaccent` extensions, trigram GIN indexes for fuzzy matching |
| `0004_prefix_tsquery_finnish.sql` | `prefix_tsquery()` for Finnish/agglutinative languages + updated `hybrid_search()` |

### Key Concepts

#### HNSW Vector Index (0000)

```sql
CREATE INDEX s3_segments_embedding_hnsw
ON s3_segments USING hnsw (embedding vector_cosine_ops);
```

Approximate nearest neighbor index for fast cosine similarity on 1536-dimensional
embeddings. Queries use the `<=>` operator for cosine distance.

#### Hybrid Search with RRF (0001)

The `hybrid_search()` function runs two parallel searches:

1. **Semantic**: cosine distance via `embedding <=> query_embedding`
2. **Keyword**: full-text search via `text_search @@ tsquery`

Results are combined using **Reciprocal Rank Fusion**:

```text
rrf_score = sem_weight / (k + sem_rank) + kw_weight / (k + kw_rank)
```

The `rrf_k=60` constant smooths rankings so top results from either method
contribute without dominating.

#### prefix_tsquery for Finnish (0004)

Standard `websearch_to_tsquery` fails for agglutinative languages like Finnish
where "xylitol" should match "xylitolin" (genitive form). The `prefix_tsquery()`
function converts each word to a prefix match:

```text
'fluoridi ksylitoli' → 'fluoridi:* & ksylitoli:*'
```

Special characters are stripped to prevent `to_tsquery()` syntax errors.

#### Trigram Fallback (0003)

`pg_trgm` GIN indexes enable `word_similarity()` and `ILIKE` searches as a
fallback when hybrid search returns too few results. The `immutable_unaccent()`
wrapper is needed because PostgreSQL index expressions require immutable functions.

### Setup

```bash
# Connect to your database and run migrations in order:
psql -d videosearch -f sql/0000_initial_schema.sql
psql -d videosearch -f sql/0001_add_fulltext_search.sql
psql -d videosearch -f sql/0002_add_subtitle_cues.sql
psql -d videosearch -f sql/0003_add_trigram_search.sql
psql -d videosearch -f sql/0004_prefix_tsquery_finnish.sql
```

### Example Query

```sql
-- Hybrid search: combine semantic + keyword with RRF
SELECT * FROM hybrid_search(
    'dental implant',                     -- keyword query
    '<embedding_vector>'::vector(1536),   -- embedding from your model
    20,                                   -- limit
    0.5,                                  -- semantic weight
    0.5,                                  -- keyword weight
    60                                    -- RRF k constant
);
```

### Relationship to PgVectorStore Python Class

The Python `PgVectorStore` class (documented above) implements similar concepts
(HNSW index, FTS, hybrid RRF) for a **generic document store**. These SQL scripts
are a **video-specific implementation** with domain tables (videos, segments, cues)
and Finnish language optimizations. Use the Python class for general RAG; use
these SQL scripts as reference when building a video search system.
