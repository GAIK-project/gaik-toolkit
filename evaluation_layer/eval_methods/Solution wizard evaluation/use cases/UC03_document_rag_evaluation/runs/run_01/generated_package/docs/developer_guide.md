# Developer Guide — Manufacturing Knowledge Base RAG Assistant

> Package structure, extension points, component configuration, tests, and evaluation.

## Architecture
This use case is driven by an **executable JSON blueprint** (`use_case.blueprint.json`) — the single source of truth. The PoC, the visual workflows (`workflow.mmd`, `workflow.bpmn`), and these docs are all *generated from it*. To change behaviour, edit the blueprint and regenerate; never hand-edit generated artifacts.

## Pipeline
| Step | Type | Component | Inputs | Outputs |
|------|------|-----------|--------|---------|
| load_input | user_task | — <br/>opts: cli_arg=--input <path-to-poc_input_bundle.json>, path_resolution=all other files resolved relative to poc_input_bundle.json | — | poc_input_bundle, document_collection, access_manifest, query_set |
| ingest_and_index | automated_task | custom <br/>opts: chunking_strategy=structure_aware, chunk_overlap=moderate, metadata_fields=['file_name', 'page_number', 'classification', 'allowed_roles'], embedding_model=from_env_AZURE_EMBEDDING_DEPLOYMENT, provider=azure_openai | document_collection, access_manifest | chunked_documents, local_vector_index |
| apply_rbac_and_retrieve | automated_task | custom <br/>opts: role_source=trusted_request_metadata, filter_timing=pre_retrieval, top_k=4, similarity_metric=cosine, denied_handling=return_denied_record_immediately | local_vector_index, query_set | retrieved_chunks_per_query |
| generate_answers | automated_task | custom <br/>opts: model=gpt-5.4, temperature=0.0, reasoning_effort=medium, provider=azure_openai, citation_format=[file_name, page_number], grounding_policy=retrieved_content_only, no_support_policy=state_not_found_do_not_speculate, output_path=output/results.json | retrieved_chunks_per_query, query_set | rag_answer_records |

### Components and their options
- **RBACPreFilter** (custom)
- **LocalVectorIndexer** (custom)
- **CitedRAGPipeline** (custom)

- **LocalVectorIndexer** — `chunk_size=400` tokens, `overlap=80` tokens (≈20%), structure-aware splitting on paragraph boundaries (`\n\n`). Embeddings are generated in batches of 16 via `client.embeddings.create(model=AZURE_EMBEDDING_DEPLOYMENT)`. The full embedding matrix is kept in memory as a numpy `float32` array. Configured in `config.yaml → rag:` and overridden by the `AZURE_EMBEDDING_DEPLOYMENT` env var.
- **RBACPreFilter** — `role_source: trusted_request_metadata` (taken from query dict, never inferred from question text). Per query: embeds the question, computes cosine similarity against **all** chunks (including restricted), checks the top-1 result's `allowed_roles`. If the role is absent → `denied` immediately, no content forwarded to the model. Otherwise → filters chunk pool to `role in chunk["allowed_roles"]` and retrieves top-`k=4`. Configured in `config.yaml → rag.top_k`.
- **CitedRAGPipeline** — `model=gpt-5.4`, `temperature=0.0`, `reasoning_effort=medium` passed as a kwarg to `chat.completions.create()`. Citations are extracted by regex pattern `[filename.ext, N]` and validated against the retrieved chunk set; unvalidated citations are silently dropped to prevent fabrication. Configured in `config.yaml → models:` and `AZURE_CHAT_DEPLOYMENT` env var.

## Layout (PoC)
```
poc/
  run_poc.py            <- pipeline entry point
  config.yaml           <- model names, temperature, paths
  requirements.txt
  .env.example
  schemas/              <- output_schema.py (Pydantic) + requirements + hash
  prompts/              <- extraction_requirements.md, validation_rubric.md
  sample_input/  output/
  evals/                <- run_basic_eval.py
```

## Extension points
- **Add/replace a component:** update `components` + `workflow.steps` + `artifacts` in the blueprint, re-validate, regenerate.
- **Change the schema/fields:** edit `target_output_spec` (and `prompts/extraction_requirements.md`); the schema regenerates on the next run via the requirements hash.
- **Tune a component option:** set it in `workflow.steps[].parameters` (e.g. `enhanced_transcript`, `include_verification`, `hybrid_search`).

## Configuration
- **Model provider:** azure_openai
- **Model preferences:** answer_model: gpt-5.4, temperature: 0.0, reasoning_effort: medium, embedding_model: from_env_AZURE_EMBEDDING_DEPLOYMENT
- **Integration targets:** _none_

## Tests and evaluation
- Evaluation requirements: method: deterministic query testing, queries: ['Q01', 'Q02', 'Q03', 'Q04'], expected_outputs: defined in poc_input_bundle.json and query_set.json, numerical_threshold: not_specified, eval_framework: RAG_eval
- See `evals/` for the basic evaluation script and `evaluation_plan.md` for the full plan.

**Known gotchas:**
- `reasoning_effort` is forwarded directly to the Azure OpenAI API. If the chat deployment does not support it (e.g. an older gpt-4o deployment), the API will return a 400 error. Remove or comment out the kwarg in `generate_cited_answer()` if needed.
- Citation extraction is regex-based (`[filename.ext, N]`). If the model outputs citations in a different format (e.g. `(travel_policy.pdf, p.3)`), they will not be captured. Tighten or expand the regex in `_extract_validated_citations()` if formatting varies.
- The RBAC access gate checks the **top-1 overall** similarity match. If a query is genuinely ambiguous between a restricted and a permitted document (very similar cosine scores), the gating decision may flip unpredictably. For production, consider a configurable margin threshold.
- The entire embedding matrix is held in memory. For large document collections this may require chunking the index or switching to an on-disk store; replace `build_index()` and `cosine_similarities()` accordingly without changing the RBAC or answer-generation logic.
