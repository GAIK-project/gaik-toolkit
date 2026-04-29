# RAG Building Blocks API Reference

Detailed API documentation for GAIK RAG building blocks.

**Source:** `gaik.software_components.RAG.*`

## Contents

- [Embedder](#embedder) (text embeddings, batch embedding)
- [VectorStore](#vectorstore-in-memory--chroma) (in-memory, Chroma persistence)
- [PgVectorStore](#pgvectorstore-postgresql--pgvector) (PostgreSQL, hybrid search, RRF)
- [FinnishTextProcessor](#finnishtextprocessor) (Finnish lemmatization + compound splitting for hybrid search)
- [Retriever](#retriever) (semantic + hybrid search, reranking)
- [AnswerGenerator](#answergenerator) (LLM response, citations, streaming)
- [RAG Parsers](#rag-parsers) (VisionRagParser, DoclingRagParser)
- [Import Patterns](#import-patterns)

---

## Embedder

**Source:** `gaik.software_components.RAG.embedder`
**Install:** `pip install "gaik[embedder]"`

```python
from gaik.software_components.RAG.embedder import Embedder
from gaik.software_components.config import get_openai_config

config = get_openai_config(use_azure=True)
embedder = Embedder(config=config, model="text-embedding-3-large", batch_size=100)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | dict | required | OpenAI/Azure config from `get_openai_config()` |
| `model` | str\|None | `"text-embedding-3-large"` | Embedding model name |
| `batch_size` | int | 100 | Batch size for embedding calls |

**Methods:**

- `embed(documents, batch_size=None)` - Embed documents or raw strings
  - Accepts `list[Document]` or `list[str]`
  - Returns `tuple[list[list[float]], list[Document]]`
  - Includes automatic retry with exponential backoff on rate limits

- `embed_query(query)` - Embed a single query string
  - Returns `list[float]`

### Convenience Function

```python
from gaik.software_components.RAG.embedder import embed_texts

embeddings, docs = embed_texts(["text1", "text2"], use_azure=True, model="text-embedding-3-large")
```

---

## VectorStore (In-Memory + Chroma)

**Source:** `gaik.software_components.RAG.vector_store`
**Install:** `pip install "gaik[vector-store]"`

```python
from gaik.software_components.RAG.vector_store import VectorStore

# In-memory (no persistence)
store = VectorStore(persist=False)

# Chroma persistence
store = VectorStore(persist=True, persist_path="chroma_store", collection_name="my_collection")
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `persist` | bool | False | Enable Chroma persistence |
| `persist_path` | str | `"chroma_store"` | Chroma storage directory |
| `collection_name` | str | `"gaik_rag"` | Collection name |

**Methods:**

- `add(documents, embeddings)` - Insert documents with embeddings
- `count()` - Return document count
- `search(query_embedding, top_k=5, filters=None)` - Cosine similarity search
  - Returns `list[tuple[Document, float]]`
  - `filters`: dict for metadata filtering (e.g. `{"category": "news"}`)

---

## PgVectorStore (PostgreSQL + pgvector)

**Source:** `gaik.software_components.RAG.pg_vector_store`
**Install:** `pip install "gaik[pg-vector-store]"`

**Requires:** PostgreSQL with extensions: `vector` (pgvector), `pg_trgm`, `unaccent`

```python
from gaik.software_components.RAG.pg_vector_store import PgVectorStore

store = PgVectorStore(
    "postgresql://user:pass@host:5432/dbname",
    table_name="documents",
    embedding_dim=1536,
    fts_language="simple",
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `connection_string` | str | required | PostgreSQL URI |
| `table_name` | str | `"documents"` | Table name (letters, digits, underscores only) |
| `embedding_dim` | int | 1536 | Embedding vector dimension (match your model) |
| `fts_language` | str | `"simple"` | PostgreSQL text search config (`"simple"`, `"english"`, `"finnish"`, etc.) |

**Context manager support:**

```python
with PgVectorStore("postgresql://...") as store:
    store.setup()
    # ... use store ...
# Connection auto-closed
```

### setup()

```python
store.setup(create_extensions=True)
```

Creates extensions, table, indexes, and SQL functions (idempotent). Set `create_extensions=False` on managed databases where extensions are pre-installed.

**Creates:**
- Table: `id`, `title`, `content`, `metadata` (JSONB), `embedding` (vector), `text_search` (tsvector GENERATED), `created_at`
- HNSW index on embeddings (cosine distance)
- GIN indexes on text_search, content (trigram), metadata

### CRUD Operations

```python
ids = store.add(documents, embeddings)  # Returns list[int] of row IDs
total = store.count()
deleted = store.delete(document_ids=[1, 2, 3])
```

### Search Methods

**`search_semantic()`** - Pure vector similarity (cosine distance)
```python
results = store.search_semantic(query_embedding, top_k=10, threshold=0.7, filters={"category": "news"})
# Returns: list[tuple[Document, similarity_score]]
```

**`search_keyword()`** - Full-text keyword search (tsvector/tsquery)
```python
results = store.search_keyword("search terms", top_k=10, filters=None)
# Returns: list[tuple[Document, ts_rank_score]]
```

**`search_hybrid()`** - Reciprocal Rank Fusion (RRF)
```python
results = store.search_hybrid(
    query_embedding, "search terms",
    top_k=10, rrf_k=60,
    semantic_weight=0.5, keyword_weight=0.5, filters=None,
)
# Returns: list[tuple[Document, rrf_score]]
```

**`search_hybrid_weighted()`** - Weighted linear combination (normalized scores)
```python
results = store.search_hybrid_weighted(
    query_embedding, "search terms",
    top_k=10, semantic_weight=0.5, keyword_weight=0.5, filters=None,
)
# Returns: list[tuple[Document, combined_score]]
```

**`search()`** - VectorStore-compatible interface (drop-in for `Retriever`)
```python
results = store.search(query_embedding, top_k=5, filters=None)
```

---

## FinnishTextProcessor

**Source:** `gaik.software_components.RAG.finnish_text_processor`
**Install:** `pip install "gaik[finnish-rag]"` (spaCy + UralicNLP) or
`pip install "gaik[finnish-rag-voikko]"` (best morphology, requires `libvoikko` system library).

Lemmatization + compound splitting for Finnish hybrid search. Plugs into
`PgVectorStore` via the `text_processor` argument so inflected forms ("kissan",
"kissoilla" → "kissa") and compound parts ("kerrostalo" → "kerros" + "talo")
match between query and indexed content.

```python
from gaik.software_components.RAG.finnish_text_processor import FinnishTextProcessor
from gaik.software_components.RAG.pg_vector_store import PgVectorStore

processor = FinnishTextProcessor(backend="auto")  # voikko → spacy → uralic → simple
print(processor.lemmatize("kerrostalon kissoilla"))
# → ["kerros", "talo", "kissa"]   (Voikko)

with PgVectorStore(conn_str, text_processor=processor) as store:
    store.setup()
    store.add(documents, embeddings)
    results = store.search_hybrid(q_vec, "kerrostalon kissoilla", top_k=5)
```

| Backend | Compound splitting | Install |
|---|---|---|
| `voikko`  | ✅ | `gaik[finnish-rag-voikko]` + `apt install libvoikko1` |
| `spacy`   | ❌ | `gaik[finnish-rag]` + `python -m spacy download fi_core_news_md` |
| `uralic`  | ❌ | `gaik[finnish-rag]` |
| `simple`  | ❌ | always available — regex tokenizer + lowercase fallback |

Standalone API: `lemmatize(text) -> list[str]`, `to_tsvector_text(text) -> str`,
`expand_query(text) -> str`. The `text_processor` parameter on `PgVectorStore`
adds a `content_lemmatized` column and routes both ingest and queries through
the processor.

---

## Retriever

**Source:** `gaik.software_components.RAG.retriever`
**Install:** `pip install "gaik[retriever]"`

```python
from gaik.software_components.RAG.retriever import Retriever

retriever = Retriever(
    embedder=embedder,
    vector_store=store,       # VectorStore or PgVectorStore
    hybrid_search=False,
    re_rank=False,
    rerank_model="cross-encoder/ms-marco-MiniLM-L-12-v2",
    top_k=5,
    score_threshold=None,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `embedder` | Embedder | required | Embedder instance |
| `vector_store` | VectorStore\|PgVectorStore | required | Any store with `search()` method |
| `hybrid_search` | bool | False | Combine vector + BM25 scoring |
| `re_rank` | bool | False | Cross-encoder reranking (requires `sentence-transformers`) |
| `rerank_model` | str | `"cross-encoder/ms-marco-MiniLM-L-12-v2"` | Reranking model |
| `top_k` | int | 5 | Default number of results |
| `score_threshold` | float\|None | None | Minimum relevance score |

**search() method:**

```python
documents = retriever.search(
    "What are the key findings?",
    top_k=5,
    score_threshold=0.5,
    filters={"document_name": "report"},
    include_scores=True,     # Sets doc.metadata["relevance_score"]
    hybrid_search=True,      # Override constructor default
    re_rank=True,            # Override constructor default
)
# Returns: list[Document]
```

---

## AnswerGenerator

**Source:** `gaik.software_components.RAG.answer_generator`
**Install:** `pip install "gaik[answer-generator]"`

```python
from gaik.software_components.RAG.answer_generator import AnswerGenerator

generator = AnswerGenerator(
    config=config,
    citations=True,
    stream=True,
    conversation_history=False,
    last_n=10,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | dict\|None | None | OpenAI config (auto-fetched if None) |
| `use_azure` | bool | True | Used when config is None |
| `model` | str\|None | None | Override model from config |
| `citations` | bool | False | Include `[document_name, page X]` citations |
| `prompt` | str\|None | None | Custom prompt template (use `{query}` and `{context}` placeholders) |
| `stream` | bool | True | Stream response tokens |
| `conversation_history` | bool | False | Maintain multi-turn conversation context |
| `last_n` | int | 10 | Number of history turns to retain |

**generate() method:**

```python
# Non-streaming
answer = generator.generate("What is the summary?", documents, stream=False)
# Returns: str

# Streaming
for chunk in generator.generate("What is the summary?", documents, stream=True):
    print(chunk, end="")
# Returns: Iterable[str]

# Context can be str or list[Document]
answer = generator.generate("Question?", "Plain text context", stream=False)
```

---

## RAG Parsers

### VisionRagParser

**Source:** `gaik.software_components.RAG.rag_parser_vision`
**Install:** `pip install "gaik[rag-parser-vision]"`

Combines Docling structure analysis with vision model for image/chart interpretation.

```python
from gaik.software_components.RAG.rag_parser_vision import VisionRagParser

parser = VisionRagParser(
    vision_config=config,
    enable_ocr=True,
    ocr_engine="tesseract_cli",
    enable_table_structure=True,
    verbose=True,
)

chunks = parser.convert_doc_to_chunks_with_vision("document.pdf")
# Returns: list[Document] with page_content including [IMAGE DESCRIPTIONS]
```

**Chunk metadata:** `source`, `document_name`, `page_number`, `heading`, `chunk_id`

**Convenience function:**
```python
from gaik.software_components.RAG.rag_parser_vision import parse_doc_to_chunks_with_vision

chunks = parse_doc_to_chunks_with_vision("document.pdf", vision_config=config)
```

### DoclingRagParser

**Source:** `gaik.software_components.RAG.rag_parser_docling`
**Install:** `pip install "gaik[rag-parser-docling]"`

Docling-based parser with HierarchicalChunker for structure-aware chunking.

```python
from gaik.software_components.RAG.rag_parser_docling import DoclingRagParser

parser = DoclingRagParser(
    enable_ocr=True,
    ocr_engine="tesseract_cli",
    enable_table_structure=True,
    enable_formula_enrichment=True,
    num_threads=4,
)

# Convert to markdown
markdown = parser.convert_pdf_to_markdown("document.pdf", output_path="output.md")

# Convert to RAG chunks with metadata (HierarchicalChunker)
chunks = parser.convert_pdf_to_chunks_with_metadata("document.pdf")
# Returns: list[Document]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_ocr` | bool | True | Enable OCR for scanned documents |
| `ocr_engine` | str | `"tesseract_cli"` | OCR engine: `tesseract_cli`, `tesseract`, `easyocr`, `rapidocr` |
| `enable_table_structure` | bool | True | Table structure recognition |
| `enable_formula_enrichment` | bool | True | Formula enrichment |
| `num_threads` | int | 4 | Accelerator threads |

**Chunk metadata:** `source`, `document_name`, `page_number`, `heading`, `chunk_id`

**Convenience functions:**
```python
from gaik.software_components.RAG.rag_parser_docling import (
    parse_pdf_to_markdown,
    parse_pdf_to_chunks_with_metadata,
)

markdown = parse_pdf_to_markdown("document.pdf")
chunks = parse_pdf_to_chunks_with_metadata("document.pdf")
```

---

## Import Patterns

```python
# Embedder
from gaik.software_components.RAG.embedder import Embedder, embed_texts

# VectorStore (Chroma)
from gaik.software_components.RAG.vector_store import VectorStore

# PgVectorStore (PostgreSQL)
from gaik.software_components.RAG.pg_vector_store import PgVectorStore

# Retriever
from gaik.software_components.RAG.retriever import Retriever

# Answer Generator
from gaik.software_components.RAG.answer_generator import AnswerGenerator

# RAG Parsers
from gaik.software_components.RAG.rag_parser_vision import VisionRagParser
from gaik.software_components.RAG.rag_parser_docling import DoclingRagParser

# Shared config
from gaik.software_components.config import get_openai_config, create_openai_client
```
