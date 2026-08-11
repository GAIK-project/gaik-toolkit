# Technical Specification — Manufacturing Internal Knowledge Assistant

> Generated from `use_case.blueprint.json`. Source of truth is the blueprint; regenerate after any change.

## Overview
Role-aware RAG assistant that answers employee questions over internal manufacturing policies, equipment manuals, and management documents with citations and enforced role-based access control.

- **Use-case id:** `manufacturing_rag_assistant`
- **Domain:** manufacturing
- **Primary language:** en
- **Runtime interface:** cli

## Inputs and outputs
- **Input types:** pdf, document_collection, text
- **Input formats:** pdf, json
- **Output types:** structured_json
- **Data sources:** local_file_bundle

## Selected components
- **RAGWorkflow** (module) — Use case is document Q&A with citations over a local document collection. RAGWorkflow covers the full indexing (chunking, embedding, storage) and retrieval-augmented generation pipeline. Citations are required and enabled. RBAC metadata filtering is implemented at the PoC level using the Chroma store metadata filter on allowed_roles.

**RAGWorkflow** — selected because the use case is document Q&A with citations over a local document collection; covers the full indexing → retrieval → generation pipeline in one module. Non-default options: `citations=True` (explicit citation requirement), `retriever_top_k=4` (user-specified top-4 chunks), `conversation_history=False` (batch CLI, not conversational), `stream=False` (batch pipeline), `collection_name="manufacturing_knowledge"`. RBAC is implemented at the PoC level: the `document_name` Chroma metadata field is used as a pre-retrieval role filter via the `filters` parameter of `ask()`.

## Workflow
| Step | Type | Component | Inputs | Outputs |
|------|------|-----------|--------|---------|
| load_input_bundle | user_task | — <br/>opts: entrypoint_flag=--input, description=User provides path to poc_input_bundle.json via CLI. All referenced files (PDFs, access_manifest.json, query_set.json) are resolved relative to the bundle file. | — | poc_input_bundle, document_collection, access_manifest, query_set |
| run_rag_pipeline | automated_task | RAGWorkflow <br/>opts: collection_name=manufacturing_knowledge, citations=True, conversation_history=False, stream=False, retriever_top_k=4, persist=True, rbac_metadata_fields=['classification', 'allowed_roles', 'file_name', 'page_number'], chunking_strategy=structure_aware, chunk_overlap=moderate, role_filter_field=allowed_roles, role_source=query_metadata, deny_when_no_allowed_chunks=True, citation_format=[file_name, page_number], citation_page_type=1-based integer, preserve_exact_values=True, no_speculation=True | document_collection, access_manifest, query_set | answer_records |
| save_results | automated_task | — <br/>opts: output_file=output/results.json, format=json_array | answer_records | saved_results |

### Artifacts
- `poc_input_bundle` — text, source: user_upload
- `document_collection` — document_collection, source: user_upload
- `access_manifest` — text, source: user_upload
- `query_set` — text, source: user_upload
- `answer_records` — answer_with_citations, source: generated
- `saved_results` — structured_json, source: generated (final output)

## Output schema
- **Schema name:** RAGAnswerRecord
- **Field count:** 7
- **Required fields:** query_id, role, question, access_decision, answer, citations
- **Missing-value policy:** _not specified_

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
- Allowed factual answers require at least one citation
- Each citation must be a two-element list [string file_name, integer page_number] with 1-based page number
- Denied answers require refusal_reason, empty citations list, and must not reveal restricted content
- Do not answer from model memory when authorized evidence is absent

## Model configuration
- **Model provider:** azure_openai
- **Model preferences:** generation_model: gpt-5.4, temperature: 1.0, reasoning_effort: medium, embedding_model: ${AZURE_OPENAI_EMBEDDING_DEPLOYMENT}

## Runtime and integration assumptions
- **Integration targets:** _none_
- **Human review:** no

## Security and governance
- **Security constraints:** Role-based access control enforced via per-chunk allowed_roles metadata stored in the vector index. Role is trusted request metadata supplied with each query and must never be inferred from question content. Role filter applied before similarity retrieval so only chunks where allowed_roles contains the query role are candidates. Management-confidential documents (project_aurora_pricing_strategy.pdf) are never retrieved or disclosed to users with the 'employee' role.
- **Contains personal data:** unknown
- **Output sensitivity:** high
- **Audit log required:** no

## Evaluation method
Four role-tagged queries (Q01-Q04) with exact expected access decisions, answer content, and citation pairs. Q01 (employee, Helsinki hotel limit): access=allowed, EUR 180/night + Finance Director approval, cite [employee_travel_policy.pdf, 3]. Q02 (employee, MX-200 filter): access=allowed, 250h inspection + 1000h or 1.8bar replacement, cite [mx200_maintenance_manual.pdf, 3] and [mx200_maintenance_manual.pdf, 4]. Q03 (employee, Project Aurora ceiling): access=denied, empty citations, no 12%/22%/CFO details. Q04 (manager, Project Aurora ceiling and approver): access=allowed, 12% ceiling + CFO written approval, cite [project_aurora_pricing_strategy.pdf, 3].
