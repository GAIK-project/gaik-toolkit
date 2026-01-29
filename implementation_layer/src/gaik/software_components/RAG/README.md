# RAG Building Blocks

This folder contains RAG-focused software components that share a common data
contract based on `langchain_core.documents.Document`.

## Available software components

- **rag_parser_docling**: Parse PDFs with Docling and produce chunked Documents
  with metadata.
- **rag_parser_vision**: Docling + vision model parsing that adds concise image
  descriptions into chunk text.
- **embedder**: Generate embeddings from text chunks using OpenAI/Azure models.
- **vector_store**: Store embeddings and metadata (in-memory or Chroma persistent).
- **retriever**: Retrieve relevant chunks (semantic, optional hybrid + rerank).
- **answer_generator**: Generate answers from retrieved context with optional
  citations and conversation history.

See each subfolder for a full README and usage examples.
