# RAG Component Examples

This folder contains examples for each of the five RAG (Retrieval-Augmented Generation) components used to build question-answering systems over document collections.

## Files

- `rag_parser_vision_example.py` - Parse documents using vision-based extraction for complex layouts
- `rag_parser_docling_example.py` - Parse documents using Docling for fast local processing
- `embedder_example.py` - Generate vector embeddings from text chunks
- `vector_store_example.py` - Store and manage document embeddings in ChromaDB
- `pg_vector_store_example.py` - PostgreSQL vector store with semantic, keyword, and hybrid search
- `retriever_example.py` - Search and retrieve relevant document chunks (with optional reranking)
- `answer_generator_example.py` - Generate contextual answers with citations from retrieved chunks

## What These Examples Show

- How to parse and chunk documents for RAG pipelines
- How to generate embeddings and store them in a vector database
- How to use PostgreSQL with pgvector for semantic and hybrid search
- How to retrieve relevant document chunks using semantic search
- How to generate answers with source citations
- How each RAG component works independently before combining them in a full pipeline

## Usage

```bash
# Run individual component examples
python rag_parser_vision_example.py
python rag_parser_docling_example.py
python embedder_example.py
python vector_store_example.py
python pg_vector_store_example.py  # requires PostgreSQL with pgvector
python retriever_example.py
python answer_generator_example.py
```

## Related Documentation

- [RAG Components](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/src/gaik/software_components/RAG)
- [Software Components Overview](https://gaik-project.github.io/gaik-toolkit/toolkit/software-components#rag-components)
- [RAG-Workflow Module](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/examples/software_modules/RAG_workflow)
