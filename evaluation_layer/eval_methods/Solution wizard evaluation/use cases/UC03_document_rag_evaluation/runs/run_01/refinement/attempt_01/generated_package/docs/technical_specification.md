# Technical Specification — Manufacturing Knowledge Base RAG Assistant

> Generated from `use_case.blueprint.json`. Source of truth is the blueprint; regenerate after any change.

## Overview
Role-aware question-answering assistant that retrieves cited answers from internal manufacturing policies, equipment manuals, and management documents, with pre-retrieval RBAC to enforce document access boundaries.

- **Use-case id:** `manufacturing_knowledge_rag`
- **Domain:** manufacturing
- **Primary language:** en
- **Runtime interface:** cli

## Inputs and outputs
- **Input types:** pdf, json
- **Input formats:** PDF (text-based, 1-based page numbers), JSON (access_manifest, query_set, poc_input_bundle)
- **Output types:** structured_json
- **Data sources:** local file bundle resolved relative to poc_input_bundle.json at runtime

## Selected components
- **RBACPreFilter** (custom)
- **LocalVectorIndexer** (custom)
- **CitedRAGPipeline** (custom)

- **LocalVectorIndexer** — selected because the standard `RAGWorkflow` module requires PostgreSQL + pgvector (out of PoC scope); implements structure-aware PDF chunking (~400 token chunks, ~80 token overlap) with Azure OpenAI embeddings stored in a numpy in-memory index. Embedding deployment name is read from `AZURE_EMBEDDING_DEPLOYMENT` env var.
- **RBACPreFilter** — no GAIK registry component provides pre-retrieval access control; reads `access_manifest.json` at index time, attaches `allowed_roles` to every chunk, and gates each query by comparing the top-1 overall similarity match against the requestor's role before any content reaches the model. Role is taken from trusted request metadata only.
- **CitedRAGPipeline** — retrieves top-4 permitted chunks by cosine similarity, generates answers with gpt-5.4 (temperature=0.0, reasoning_effort=medium) strictly grounded in retrieved content, and extracts `[file_name, page_number]` citations validated against the retrieved chunk set to prevent fabrication.

## Workflow
| Step | Type | Component | Inputs | Outputs |
|------|------|-----------|--------|---------|
| load_input | user_task | — <br/>opts: cli_arg=--input <path-to-poc_input_bundle.json>, path_resolution=all other files resolved relative to poc_input_bundle.json | — | poc_input_bundle, document_collection, access_manifest, query_set |
| ingest_and_index | automated_task | custom <br/>opts: chunking_strategy=structure_aware, chunk_overlap=moderate, metadata_fields=['file_name', 'page_number', 'classification', 'allowed_roles'], embedding_model=from_env_AZURE_EMBEDDING_DEPLOYMENT, provider=azure_openai | document_collection, access_manifest | chunked_documents, local_vector_index |
| apply_rbac_and_retrieve | automated_task | custom <br/>opts: role_source=trusted_request_metadata, filter_timing=pre_retrieval, top_k=4, similarity_metric=cosine, denied_handling=return_denied_record_immediately | local_vector_index, query_set | retrieved_chunks_per_query |
| generate_answers | automated_task | custom <br/>opts: model=gpt-5.4, temperature=0.0, reasoning_effort=medium, provider=azure_openai, citation_format=[file_name, page_number], grounding_policy=retrieved_content_only, no_support_policy=state_not_found_do_not_speculate, output_path=output/results.json | retrieved_chunks_per_query, query_set | rag_answer_records |

### Artifacts
- `poc_input_bundle` — json, source: user_upload
- `document_collection` — document_collection, source: user_upload
- `access_manifest` — json, source: user_upload
- `query_set` — json, source: user_upload
- `chunked_documents` — text_chunks, source: generated
- `local_vector_index` — vector_index, source: generated
- `retrieved_chunks_per_query` — text_chunks, source: generated
- `rag_answer_records` — structured_json, source: generated (final output)

## Output schema
- **Schema name:** RAGAnswerRecord
- **Field count:** 7
- **Required fields:** query_id, role, question, access_decision, answer, citations
- **Missing-value policy:** If authorized sources do not support an answer, state the information was not found and do not speculate. Do not fabricate citations.

**Fields:**
- query_id
- role
- question
- access_decision
- answer
- citations
- refusal_reason

**Validation rules:**
- access_decision must be 'allowed' or 'denied'
- citations must be an empty list when access_decision=denied
- refusal_reason must be non-null when access_decision=denied
- each citation must be exactly [str, int] (filename, 1-based page number)
- answer must not reveal restricted content when access_decision=denied
- allowed factual answers must include at least one citation to a document permitted for that role
- exact values must be preserved: EUR 180, 250 operating hours, 1,000 operating hours, 1.8 bar, 12 percent, 22 percent

## Model configuration
- **Model provider:** azure_openai
- **Model preferences:** answer_model: gpt-5.4, temperature: 0.0, reasoning_effort: medium, embedding_model: from_env_AZURE_EMBEDDING_DEPLOYMENT

## Runtime and integration assumptions
- **Integration targets:** _none_
- **Human review:** no

## Security and governance
- **Security constraints:** RBAC pre-filter: role from trusted request metadata (not inferred from question); access_manifest.json maps documents to allowed_roles; unauthorized chunks must never enter model context, Cloud LLM API calls to Azure OpenAI are permitted, No personal data in synthetic PoC fixtures, No audit-log service required for PoC; enterprise identity integration is out of PoC scope
- **Contains personal data:** false
- **Output sensitivity:** mixed
- **Audit log required:** no

## Evaluation method
method: deterministic query testing, queries: ['Q01', 'Q02', 'Q03', 'Q04'], expected_outputs: defined in poc_input_bundle.json and query_set.json, numerical_threshold: not_specified, eval_framework: RAG_eval
