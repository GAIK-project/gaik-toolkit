# Evidence alignment prompt

For every UC03 oracle check, locate the closest generated value and concrete evidence in the conversation, blueprint, generated package, validator output, or PoC execution record. Preserve semantic equivalence but do not assign the final Yes/No verdict. For RAG checks, identify configuration for parsing, chunk metadata, embeddings, access filtering, retrieval, answer grounding, citations, and CLI execution. Report NOT FOUND when no evidence exists.
