# The same design without gaik

Read this when building hybrid search in a TypeScript or other non-Python app, when an
embedding has more than 2,000 dimensions, or when writing the SQL by hand. The design is the
one `PgVectorStore` implements; this is its shape in plain Postgres.

## Contents
- Schema
- Column type by dimension
- Indexes and database defaults
- The OR tsquery
- The hybrid query
- One statement per mode
- Filters
- Health checks
- TypeScript notes

## Schema

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (
  id         BIGSERIAL PRIMARY KEY,
  title      TEXT NOT NULL,
  source_url TEXT,
  meta       JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE chunks (
  id             BIGSERIAL PRIMARY KEY,
  document_id    BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index    INTEGER NOT NULL,
  context_prefix TEXT,          -- heading path; embedded with the body, stored apart
  content        TEXT NOT NULL,
  embedding      halfvec(1536),
  fts tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('finnish', coalesce(context_prefix, '')), 'A') ||
    setweight(to_tsvector('finnish', coalesce(content, '')), 'B')
  ) STORED,
  tsv_lemma      tsvector,      -- written at ingest from lemmas; NULL when not Finnish
  UNIQUE (document_id, chunk_index)
);
```

- `to_tsvector(regconfig, text)` with two arguments is IMMUTABLE and therefore allowed in a
  generated column; the one-argument form is not.
- A generated column fixes one language for every row. For a mixed-language corpus, write
  the tsvector at ingest with each row's own configuration — and weight the same fields the
  same way in every tsvector column, or a hit ranks differently depending on which arm
  found it.
- Embedding the heading path with the body gives a chunk its context; storing the body
  separately keeps the prefix out of what the reader sees.

## Column type by dimension

| Embedding dimensions | Column | HNSW operator class for `<=>` |
|---|---|---|
| up to 2,000 | `vector(N)` | `vector_cosine_ops` |
| up to 4,000 | `halfvec(N)` | `halfvec_cosine_ops` |
| more | reduce the dimensions first | — |

Models trained Matryoshka-style return a shorter prefix that is still a real embedding: ask
the provider for fewer dimensions (the OpenAI embeddings API takes `dimensions`) and 1,536
out of 3,072 costs close to nothing while halving storage. To keep full precision on disk,
store `vector(3072)`, index the cast — `USING hnsw ((embedding::halfvec(3072))
halfvec_cosine_ops)` — and cast identically in every query, or the planner ignores the
index.

pgvector fixes the dimension on the column. To compare embedding models, give each model
its own table keyed by chunk id rather than one table with a model column.

## Indexes and database defaults

```sql
CREATE INDEX chunks_embedding_hnsw ON chunks USING hnsw (embedding halfvec_cosine_ops);
CREATE INDEX chunks_fts_gin        ON chunks USING gin (fts);
CREATE INDEX chunks_lemma_gin      ON chunks USING gin (tsv_lemma) WHERE tsv_lemma IS NOT NULL;
CREATE INDEX chunks_document_id    ON chunks (document_id);

ALTER DATABASE search SET hnsw.ef_search = 100;
ALTER DATABASE search SET hnsw.iterative_scan = 'relaxed_order';   -- pgvector 0.8+
```

- The operator class must match the query operator. An index built with `*_l2_ops` and
  queried with `<=>` is not used, and every search scans the table without complaint.
- `hnsw.ef_search` defaults to 40. On one 53,803-vector corpus that stopped at 73.9%
  recall@15 where 100 matched an exact scan (75.0%) and still ran 3.4× faster than it — a
  silent 1.1 points. It is the first setting to check in any pgvector retrieval.
- Without `iterative_scan`, a filtered vector query returns fewer rows than it asked for.
- Drop the HNSW index before a bulk load and rebuild it after: maintaining it during a
  37,000-row insert roughly tripled ingest time.
- Database defaults cover psql sessions and future services; still set the values per
  connection if a pooler might hand out connections from another database.

## The OR tsquery

```sql
-- websearch parsing keeps stemming, stop words and quoted phrases; then OR the terms.
-- A leading '-' is dropped first (see below); a dash inside a word is kept.
CREATE OR REPLACE FUNCTION or_tsquery(cfg regconfig, q text)
RETURNS tsquery LANGUAGE sql IMMUTABLE AS $$
  SELECT NULLIF(replace(
    websearch_to_tsquery(cfg, regexp_replace(q, '(^|\s)-+', '\1', 'g'))::text,
    ' & ', ' | '
  ), '')::tsquery
$$;
```

A query of pure stopwords yields NULL here, which matches nothing without raising. Rank
with `ts_rank_cd`: it scores by how many distinct terms matched and how close together.

Drop the minus signs before parsing. `websearch_to_tsquery` reads a leading `-` as NOT, and
so does a spaced dash: `Kela - asumistuki` parses as `'kela' & !'asumistuki'`. Rewriting
that `&` to `|` gives `'kela' | !'asumistuki'`, which matches nearly every row in the table.
Nobody typing a sentence into a search box meant an exclusion; if the app needs one,
apply it as a separate `AND NOT fts @@ …` condition.

## The hybrid query

```sql
-- $1 query vector '[...]'  $2 query text  $3 candidates per arm (e.g. 100)
-- $4 RRF k  $5 vector weight  $6 result limit
WITH vector_hits AS (
  SELECT id, distance, ROW_NUMBER() OVER (ORDER BY distance, id) AS rank
  FROM (
    SELECT c.id, c.embedding <=> $1::halfvec AS distance
    FROM chunks c
    WHERE c.embedding IS NOT NULL
    ORDER BY c.embedding <=> $1::halfvec
    LIMIT $3
  ) v
),
keyword_hits AS (
  SELECT id, ROW_NUMBER() OVER (ORDER BY score DESC, id) AS rank
  FROM (
    SELECT c.id, ts_rank_cd(c.fts, q.tsq) AS score
    FROM chunks c, LATERAL (SELECT or_tsquery('finnish', $2) AS tsq) q
    WHERE c.fts @@ q.tsq
    ORDER BY score DESC, c.id
    LIMIT $3
  ) k
),
fused AS (
  SELECT COALESCE(v.id, k.id) AS id,
         $5 * COALESCE(1.0 / ($4 + v.rank), 0) + COALESCE(1.0 / ($4 + k.rank), 0) AS score,
         v.rank AS vector_rank, k.rank AS keyword_rank, v.distance
  FROM vector_hits v FULL OUTER JOIN keyword_hits k ON v.id = k.id
)
SELECT c.id, c.document_id, c.content, f.score, f.vector_rank, f.keyword_rank, f.distance
FROM fused f JOIN chunks c ON c.id = f.id
ORDER BY f.score DESC
LIMIT $6;
```

Return both ranks and the distance. The ranks show an arm that contributes nothing; the
distance feeds the relevance floor, which the fused score cannot. Tune `$4` and `$5` on the
eval set — equal weights are a guess.

## One statement per mode

Postgres cannot infer the type of a placeholder that never appears in the statement, so a
vector-only or keyword-only variant sharing the hybrid query's numbering fails to prepare:
`could not determine data type of parameter $N`. Give each mode its own statement and
numbering, and map mode names explicitly — a new mode that falls through to a default runs
the wrong query without an error.

## Filters

Apply metadata filters inside **both** arms, before their `LIMIT`. Filtering after fusion
shrinks the page below the limit and can empty it.

## Health checks

```sql
-- 's' means a stored generated column; '' means a plain column nothing fills
SELECT attgenerated FROM pg_attribute
WHERE attrelid = 'chunks'::regclass AND attname = 'fts';

-- rows the keyword arm cannot see
SELECT count(*) FROM chunks WHERE fts IS NULL OR fts = ''::tsvector;
```

And one end-to-end probe from application code: take a word from a random stored chunk, run
it through the production keyword query, and assert that chunk comes back. A non-NULL column
built with the wrong configuration passes both SQL checks and fails this one.

Postgres has no `ALTER COLUMN … SET GENERATED` for a stored column. Repairing a plain column
means dropping it and adding it back as generated; the values derive from the text, so
nothing is lost, and the GIN index must be recreated.

## TypeScript notes

- node-postgres returns `BIGINT` as a string. Cast to `::int` in SQL when the ids fit, or
  convert explicitly: a strict comparison against a number silently never matches — it made
  one benchmark read 0% recall.
- Pass the query vector as a `'[0.1,0.2,…]'` literal cast to `::halfvec` or `::vector`.
- Keep tokenizers out of the request path of a server bundle; libraries that load a native
  runtime may not be present there. Truncate queries by characters and tokenize in batch jobs.
