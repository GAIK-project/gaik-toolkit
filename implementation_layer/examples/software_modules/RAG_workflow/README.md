# RAG-Workflow Module Example

This folder demonstrates how to use the RAG-Workflow module, which combines all five RAG components (Parser, Embedder, Vector Store, Retriever, Answer Generator) into a complete question-answering pipeline.

## Files

- `pipeline_example.py` - Complete example showing both indexing and query phases of the RAG workflow

## What This Example Shows

- **Phase 1: Indexing** - How to parse documents, generate embeddings, and store them in a persistent vector database
- **Phase 2: Querying** - How to retrieve relevant context and generate answers with citations
- How to use hybrid search (keyword + semantic) and reranking for better retrieval
- How to generate answers with inline source citations
- How to maintain conversation history for multi-turn dialogue
- How the vector store persists across sessions for efficient reuse

## Usage

```bash
python pipeline_example.py
```

## Module Workflow

### Indexing Phase
1. Parse PDF documents into clean text chunks
2. Generate vector embeddings for each chunk
3. Store embeddings in ChromaDB (persistent vector database)

### Query Phase
1. User submits a question
2. Retriever searches the vector store for relevant chunks
3. Optional reranking refines relevance
4. Answer Generator produces a response with citations

## Module Outputs

- **Index Result** - Number of documents and chunks indexed, vector store path
- **Answer** - Generated response with inline citations
- **Retrieved Documents** - Top-k relevant chunks used for answer generation
- **Conversation History** - Optional: Last n Q/A pairs for context-aware responses

## Related Documentation

- [RAG-Workflow Module](../../../src/gaik/software_modules/RAG_workflow)
- [Software Modules Overview](https://gaik-project.github.io/gaik-toolkit/toolkit/software-modules#rag-workflow)
- [RAG Components](../../../src/gaik/software_components/RAG)
