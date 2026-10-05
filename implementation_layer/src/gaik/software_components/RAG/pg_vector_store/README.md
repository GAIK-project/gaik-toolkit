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
    text_processor: FinnishTextProcessor | None = None,
    tsquery_mode: str = "or",
    hnsw_ef_search: int | None = None,
    vector_type: str = "vector",
    hnsw_iterative_scan: str | None = None,
)
```

> **Upgrading from 0.8.3.** `tsquery_mode` now defaults to `"or"`; pass
> `tsquery_mode="websearch"` to keep requiring every query word. A `vector`
> column above 2,000 dimensions is refused in the constructor (it could never be
> indexed); pass `vector_type="halfvec"` for those. Hybrid results gain a
> `semantic_similarity` metadata key. Nothing changes in an existing table.

### `tsquery_mode` — how a query becomes a tsquery

**`"or"` (default) lets a passage match on some of the query's words** and leaves
the ranking to `ts_rank_cd`. `"websearch"`, the default through 0.8.3, conjoins
every term. That is right for short keyword input and wrong for a sentence: a
nine-word question only matches a passage containing all nine stems, which on
real prose is never, so the keyword arm contributes nothing and does so silently.

| Mode | Behaviour | Use when |
| --- | --- | --- |
| `"or"` | Postgres' parse, `&` rewritten to `\|` | natural-language questions, and by default |
| `"websearch"` | Postgres' parser as-is (implicit AND) | short keyword queries where every term must appear |
| `"prefix"` | each term prefix-matched, OR-ed | agglutinative suffixing on an **unstemmed** index |

`"or"` keeps stemming, stop-word removal and quoted phrases — only the operator
changes — and lets `ts_rank_cd` discriminate, which it already does by how many
distinct terms matched and how close together they are.

`"or"` and `"prefix"` drop a leading `-` before parsing. Postgres reads it as NOT,
also in a spaced dash (`Kela - asumistuki`), and a negated term OR-ed with the
rest would match nearly every row. A dash inside a word (`sote-uudistus`) is kept.

Measured on four Finnish sentences plus one long natural question:

| Configuration | Queries that found their document |
| --- | --- |
| `finnish` + `"websearch"` | 2 / 5 |
| `finnish` + `"or"` | 3 / 5 |
| lemmatized both sides (`simple` + `text_processor`) + `"or"` | **5 / 5** |

`"prefix"` is a poor fit for Finnish specifically — consonant gradation means a
lemma is often not a prefix of its own inflected forms. See the
[Finnish Text Processor README](../finnish_text_processor/README.md).

> Re-run `setup()` after upgrading gaik. Keyword and hybrid searches pass the
> store's `tsquery_mode` to the SQL, and `setup()` is what installs the functions that
> accept it.
>
> Older gaik releases may share the database — a rollback, a rolling update, a
> second app — so `setup()` also keeps the hybrid signatures without
> `tsquery_mode`, forwarding them in `websearch` mode. Through gaik 0.7.2 the new
> argument had a default instead, and an older release's `setup()` then made every
> hybrid call fail as `function ... is not unique`; the current `setup()` repairs a
> database left in that state.

### `hnsw_ef_search`

pgvector defaults `hnsw.ef_search` to 40, trading recall for a latency saving
most RAG workloads would rather not take. Measured on one 1536-dimension corpus,
raising it to 100 moved recall@20 against an exact scan from **96.2% to 99.2%
for +0.7 ms median**.

```python
PgVectorStore(dsn, hnsw_ef_search=100)
```

Applied per connection. A setting the server rejects is logged as a warning and
skipped, and the connection stays usable. Behind a transaction pooler a session
setting does not stick; `health()` reports that, and the fix is a database
default (`ALTER DATABASE ... SET hnsw.ef_search = 100`).

### `vector_type`

`"vector"` (default) stores 32-bit floats and is indexed up to **2,000**
dimensions. `"halfvec"` stores 16-bit floats, takes half the space and is indexed
up to **4,000**, which is what the 3,072-dimension models need
(`text-embedding-3-large`, `gemini-embedding-001`). Needs pgvector 0.7+.

```python
PgVectorStore(dsn, embedding_dim=3072, vector_type="halfvec")
```

The type is part of the table's schema. A table created with one cannot be
searched with the other, and `health()` names the mismatch.

### `hnsw_iterative_scan`

With a selective `filters` argument, an HNSW scan picks its nearest candidates
first and applies the filter afterwards, so it returns fewer rows than asked, or
none. On a 20,000-row table with a filter matching 40 rows, a top-20 search
through the index returned 0 rows; with iterative scans it returned 20.

```python
PgVectorStore(dsn, hnsw_iterative_scan="relaxed_order")   # or "strict_order", "off"
```

Needs pgvector 0.8+. Applied per connection, like `hnsw_ef_search`.

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
| `health(*, sample_rows=5)` | Check the live table against this store's configuration; returns a `HealthReport` |
| `relemmatize(*, batch_size=500)` | Recompute the lemma column with the current `text_processor`; returns rows updated |
| `close()` | Close database connection |

### `health()` — is each arm of the search alive?

Either arm of a hybrid search can stop contributing without an error, because the
other keeps filling the page. `health()` reads the table as it really is and
compares it with how the store is configured. Call it at startup or from a status
endpoint:

```python
report = store.health()
if not report.ok:
    raise RuntimeError(f"search index is not healthy:\n{report}")
```

It reports, one sentence each:

- an embedding column of another type or dimension than the store's;
- a `text_search` column that is not generated, so nothing fills it;
- a full-text index built with another `fts_language` than queries are parsed with;
- lemmas in the index that differ from what the current `text_processor` produces
  for the same text (a changed backend, a changed `decompound`, a missing
  library), or a lemma index read without a processor, or the reverse;
- rows without an embedding, with an empty `text_search`, or without lemmas;
- a missing vector or full-text index, or a vector index whose operator class is
  not the cosine one the searches use;
- `hnsw.ef_search` or `hnsw.iterative_scan` not in effect on the connection.

`report.details` holds the raw readings (row counts, column type, pgvector
version) for logging. Nothing is written. The row counts scan the table once.

`relemmatize()` is the repair for the lemma findings: it recomputes the lemma
column for every row with the current processor and leaves the embeddings alone.

### Return Type

All search methods return `list[tuple[Document, float]]` -- a list of
(Document, score) pairs sorted by score descending.

#### Reserved metadata keys

Two keys are taken from table columns and **overwrite** any same-named key in
the row's JSONB metadata:

| Key | Source |
|-----|--------|
| `id` | The row's primary key |
| `title` | The `title` column |

`id` is what lets `Ranker.fuse()` recognise the same row across two result
lists, so keep it if you fuse `search_semantic` with `search_keyword`.

The hybrid methods additionally surface each arm's contribution:

| Method | Extra keys |
|--------|-----------|
| `search_hybrid` | `semantic_rank`, `keyword_rank`, `semantic_similarity` |
| `search_hybrid_weighted` | `semantic_score`, `keyword_score` |

A key is **omitted** (not set to `None`) when that arm did not return the row,
so `"keyword_rank" in doc.metadata` answers "did the keyword arm find this at
all".

`semantic_similarity` is the row's cosine similarity to the query, and it is set
for every row that has an embedding, including rows only the keyword arm found.
The RRF score cannot tell a real match from the nearest neighbour of gibberish,
because it is built from rank positions; the similarity can, so this is the value
to hold against a `RelevanceGate` floor.

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
