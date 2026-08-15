# Technical Specification — Manufacturing Knowledge Assistant

> Generated from `use_case.blueprint.json`. Source of truth is the blueprint; regenerate after any change.

## Overview
Role-aware assistant that answers employee questions from internal policies, equipment manuals, and management documents with citations, enforcing role-based access control so restricted documents are never retrieved or disclosed to unauthorized employees.

- **Use-case id:** `manufacturing_knowledge_assistant`
- **Domain:** manufacturing
- **Primary language:** en
- **Runtime interface:** CLI: `python run_poc.py --input <path-to-poc_input_bundle.json>`, resolving access_manifest.json, query_set.json, and the documents directory relative to that bundle file.

## Inputs and outputs
- **Input types:** document_collection, pdf
- **Input formats:** pdf (text-based, English), json (access manifest, query set, input bundle)
- **Output types:** answer_with_citations, structured_json
- **Data sources:** PoC uses a local fixture bundle: three sample PDFs (employee_travel_policy.pdf, mx200_maintenance_manual.pdf, project_aurora_pricing_strategy.pdf) plus access_manifest.json and query_set.json, all resolved relative to poc_input_bundle.json. Connection to a live enterprise document repository is out of scope for this PoC.

## Selected components
- **RAGWorkflow** (module) — Document collection to cited answer -- RAGWorkflow covers indexing, retrieval, and cited-answer generation end-to-end, using a local persistent vector store (Chroma) and supports query-time metadata filters (ask(filters=...)) which are the mechanism used for pre-retrieval RBAC enforcement.
- **RoleScopedIngestion -- attaches role_<role> boolean metadata flags to each chunk (derived from access_manifest.json allowed_roles) before embedding, using RAGWorkflow's own embedder/vector_store attributes instead of its index_documents() convenience wrapper (which has no metadata-injection hook)** (custom)
- **AccessDecisionClassifier -- an internal-only unfiltered relevance check, never exposed as content, used solely to distinguish a restricted-topic denial from an honest not-found** (custom)

- `RAGWorkflow` was selected because the use case is document-collection Q&A with citations, which the module covers end-to-end (indexing, retrieval, cited answer generation) with a local persistent vector store, matching the "may use a local vector store" requirement without needing a Postgres deployment.
- Non-default options: `retriever_top_k=4` (spec: "top four eligible chunks"), `conversation_history=False` and `stream=False` (runtime is a batch CLI over 4 independent queries, not a chat session), `use_azure=True` (matches `model_provider=azure_openai`).
- `RoleScopedIngestion` and `AccessDecisionClassifier` are not registry components — they are custom orchestration around `RAGWorkflow`'s own public building blocks (parser/embedder/vector store/retriever), added because `RAGWorkflow.index_documents()`/`ask()` have no hook for per-chunk metadata or query-time restricted-topic classification. See `run_poc.py`'s module docstring for the full rationale.
- `LLMJudge` was deliberately **not** added: `human_review = no` and no explicit quality-check request was made.

## Workflow
| Step | Type | Component | Inputs | Outputs |
|------|------|-----------|--------|---------|
| upload_documents | user_task | — | — | source_documents |
| provide_access_manifest | user_task | — | — | access_manifest |
| submit_queries | user_task | — | — | query_batch |
| generate_role_aware_answers | automated_task | RAGWorkflow <br/>opts: persist=True, persist_path=poc/chroma_store, collection_name=gaik_rag_manufacturing_kb, citations=True, retriever_top_k=4, retriever_hybrid=False, retriever_rerank=False, conversation_history=False, stream=False, use_azure=True, embedding_model=env:RAG_EMBEDDING_DEPLOYMENT (default text-embedding-3-large), access_control=Pre-retrieval RBAC: each indexed chunk is tagged with boolean role_<role> metadata flags derived from access_manifest.json's allowed_roles; ask() is called with filters={'role_<requesting_role>': true} so unauthorized chunks are excluded from the similarity search itself (Chroma 'where' clause / in-memory pre-filter), never entering the model context., denial_classification=An additional internal-only unfiltered search (never exposed as content) checks whether the best-matching chunk for the query belongs to a role-restricted document; if so, and no strong authorized match exists, access_decision is 'denied' with a generic refusal_reason; if no strong match exists anywhere, the answer states the information was not found. | source_documents, access_manifest, query_batch | answer_records |

### Artifacts
- `source_documents` — document_collection, source: user_upload
- `access_manifest` — text, source: user_upload
- `query_batch` — text, source: user_upload
- `answer_records` — answer_with_citations, source: generated (final output)

## Output schema
- **Schema name:** RAGAnswerRecord
- **Field count:** 7
- **Required fields:** query_id, role, question, access_decision, answer, citations
- **Missing-value policy:** If the authorized sources do not support an answer, state that the information was not found and do not speculate. If sources conflict, identify the conflict and cite both sources. Never fabricate a citation.

**Fields:**
- query_id
- role
- question
- access_decision
- answer
- citations
- refusal_reason

**Validation rules:**
- An allowed factual answer requires at least one citation to a document permitted for that role
- A denied answer requires an empty citations list, a non-null refusal_reason, and must not reveal restricted facts
- Each citation is a two-element list [file_name (str), page_number (1-based int)], in that order
- query_id and role must be preserved unchanged from the input query
- Cite every material factual claim using [file_name, page_number]
- Do not answer from model memory when authorized evidence is absent

## Model configuration
- **Model provider:** azure_openai
- **Model preferences:** generation_model: gpt-5.4, temperature: 1.0, reasoning_effort: medium, embedding_model: Azure OpenAI embedding deployment supported by RAGWorkflow; exact deployment name is an environment setting

## Runtime and integration assumptions
- **Integration targets:** _none_
- **Human review:** no

## Security and governance
- **Security constraints:** Role-based access filtering must occur before retrieval, so unauthorized chunks never enter the model's context window. The requesting role is trusted request metadata and must not be inferred from the question text. Denied answers must not reveal restricted facts or citations. External model APIs are allowed. The synthetic PoC fixtures contain no personal data. Enterprise identity integration and a full audit-log service are out of scope for the PoC (simulated role values, local vector store only). No exact data-retention period was specified.
- **Contains personal data:** unknown
- **Output sensitivity:** high
- **Audit log required:** yes

## Evaluation method
Deterministic acceptance test using the four supplied role-tagged queries (Q01-Q04), checked against required facts, the exact access decision (allowed/denied), and required citation pairs per query. No numerical RAG-quality threshold (e.g. a fixed recall/precision score) was specified for the first PoC.
