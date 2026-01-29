# RAG Evaluation

Evaluation methods for assessing Retrieval-Augmented Generation (RAG) pipeline quality.

## Purpose

Evaluate the accuracy, relevance, and quality of RAG-based question answering and information retrieval.

## Metrics

- **Answer Accuracy**: Correctness of generated answers
- **Retrieval Precision**: Relevance of retrieved chunks
- **Retrieval Recall**: Coverage of relevant information
- **Citation Quality**: Accuracy of source citations
- **Response Latency**: Query processing time
- **Semantic Similarity**: Embedding and retrieval quality

## Evaluation Approaches

- **Ground Truth Q&A Pairs**: Evaluate against known question-answer datasets
- **Retrieval Metrics**: Measure precision@k, recall@k, NDCG
- **Faithfulness**: Ensure answers are grounded in retrieved context
- **LLM-as-Judge**: Automated assessment of answer quality
- **Human Evaluation**: Expert review of answers and citations

## RAG Components Evaluated

- `rag_parser_docling` - Document parsing quality
- `rag_parser_vision` - Vision-enhanced parsing accuracy
- `embedder` - Embedding quality and semantic representation
- `vector_store` - Storage and retrieval performance
- `retriever` - Retrieval accuracy (semantic, hybrid, reranking)
- `answer_generator` - Answer generation quality and citations

## Related Use Cases

- Semantic video search
- Document Q&A systems
- Knowledge base interrogation

## Related Software Modules

- `RAGWorkflow` software module
