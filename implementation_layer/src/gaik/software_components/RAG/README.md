# RAG Building Blocks

This folder contains RAG-focused software components that share a common data
contract based on `langchain_core.documents.Document`.

## Available software components

- **rag_parser_docling**: Parse PDFs with Docling and produce chunked Documents
  with metadata.
- **rag_parser_vision**: Docling + vision model parsing that adds concise image
  descriptions into chunk text.
- **embedder**: Generate embeddings from text chunks with OpenAI/Azure, Google, or an embedding model on Aitta or another OpenAI-compatible server.
- **vector_store**: Store embeddings and metadata (in-memory or Chroma persistent).
- **pg_vector_store**: PostgreSQL-backed vector store with semantic, keyword, and
  hybrid search (pgvector + FTS + RRF).
- **finnish_text_processor**: Finnish lemmatization and compound splitting so the
  index and the query agree on a form. Postgres' `finnish` snowball stems
  `tilinpäätös` and `tilinpäätöksen` to *different* lexemes, so one does not find
  the other; lemmatizing both sides closes that gap.
- **retriever**: Retrieve relevant chunks (semantic, optional hybrid + rerank).
- **ranker**: Fuse, rerank and reorder result lists you already have (weighted
  RRF, cross-encoder reranking, `asc`/`desc` ordering by a metadata field).
- **relevance_gate**: Tell "the corpus answered this" apart from "here are the
  nearest neighbours", and calibrate the threshold that separates them. A vector
  index returns results for every query, so counting them proves nothing.
- **answer_generator**: Generate answers from retrieved context with optional
  citations and conversation history.

See each subfolder for a full README and usage examples.
