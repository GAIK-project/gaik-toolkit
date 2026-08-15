# Developer Guide — Manufacturing Knowledge Assistant

> Package structure, extension points, component configuration, tests, and evaluation.

## Architecture
This use case is driven by an **executable JSON blueprint** (`use_case.blueprint.json`) — the single source of truth. The PoC, the visual workflows (`workflow.mmd`, `workflow.bpmn`), and these docs are all *generated from it*. To change behaviour, edit the blueprint and regenerate; never hand-edit generated artifacts.

## Pipeline
| Step | Type | Component | Inputs | Outputs |
|------|------|-----------|--------|---------|
| upload_documents | user_task | — | — | source_documents |
| provide_access_manifest | user_task | — | — | access_manifest |
| submit_queries | user_task | — | — | query_batch |
| generate_role_aware_answers | automated_task | RAGWorkflow <br/>opts: persist=True, persist_path=poc/chroma_store, collection_name=gaik_rag_manufacturing_kb, citations=True, retriever_top_k=4, retriever_hybrid=False, retriever_rerank=False, conversation_history=False, stream=False, use_azure=True, embedding_model=env:RAG_EMBEDDING_DEPLOYMENT (default text-embedding-3-large), access_control=Pre-retrieval RBAC: each indexed chunk is tagged with boolean role_<role> metadata flags derived from access_manifest.json's allowed_roles; ask() is called with filters={'role_<requesting_role>': true} so unauthorized chunks are excluded from the similarity search itself (Chroma 'where' clause / in-memory pre-filter), never entering the model context., denial_classification=An additional internal-only unfiltered search (never exposed as content) checks whether the best-matching chunk for the query belongs to a role-restricted document; if so, and no strong authorized match exists, access_decision is 'denied' with a generic refusal_reason; if no strong match exists anywhere, the answer states the information was not found. | source_documents, access_manifest, query_batch | answer_records |

### Components and their options
- **RAGWorkflow** (module) — Document collection to cited answer -- RAGWorkflow covers indexing, retrieval, and cited-answer generation end-to-end, using a local persistent vector store (Chroma) and supports query-time metadata filters (ask(filters=...)) which are the mechanism used for pre-retrieval RBAC enforcement.
- **RoleScopedIngestion -- attaches role_<role> boolean metadata flags to each chunk (derived from access_manifest.json allowed_roles) before embedding, using RAGWorkflow's own embedder/vector_store attributes instead of its index_documents() convenience wrapper (which has no metadata-injection hook)** (custom)
- **AccessDecisionClassifier -- an internal-only unfiltered relevance check, never exposed as content, used solely to distinguish a restricted-topic denial from an honest not-found** (custom)

`VisionRagParser`, `Embedder`, `VectorStore`, and `Retriever` are constructed directly in `run_poc.py` (not via `RAGWorkflow(...)`) so that per-chunk `role_<role>` metadata can be attached at ingestion:
- `VisionRagParser(vision_config=api_config)` — parses each PDF; `document_name=<filename with extension>` is passed explicitly to `convert_doc_to_chunks_with_vision()` so citations read `employee_travel_policy.pdf`, not the extension-stripped default.
- `Embedder(config=api_config, model=embedding_model)` — `embedding_model` reads `RAG_EMBEDDING_DEPLOYMENT` from the environment (config.yaml), falling back to `text-embedding-3-large` (assumption_002).
- `VectorStore(persist=True, persist_path=poc/chroma_store, collection_name="gaik_rag_manufacturing_kb")` — local Chroma store, wiped and rebuilt at the start of every run for repeatability.
- `Retriever(embedder=embedder, vector_store=vector_store, top_k=4)` — `search(question, filters={"role_<role>": True})` is the pre-retrieval RBAC gate; a second unfiltered `search(question, filters=None)` call is internal-only, used by `AccessDecisionClassifier`'s logic and never passed to the LLM.
- Answer generation calls `client.chat.completions.create(model=..., temperature=1.0, reasoning_effort="medium", ...)` directly on the client returned by `create_openai_client(api_config)`, **not** `AnswerGenerator.generate()` — that method hardcodes `temperature=0.0` with no override, which would silently ignore the user's explicit `temperature=1.0` / `reasoning_effort=medium` requirement in `config.yaml`.

## Layout (PoC)
```
poc/
  run_poc.py            <- pipeline entry point (RBAC-aware RAG, see classify_and_answer())
  config.yaml           <- provider, model, temperature, reasoning_effort, paths
  requirements.txt
  .env.example
  schemas/               <- output_schema.py (hand-authored RAGAnswerRecord Pydantic model)
  sample_input/          <- poc_input_bundle.json + poc_input/ (access_manifest.json, query_set.json, documents/*.pdf)
  output/                <- answer_records.json (+ chroma_store/, rebuilt each run)
  evals/                 <- run_basic_eval.py + ground_truth/expected_results.json
```

## Extension points
- **Add/replace a component:** update `components` + `workflow.steps` + `artifacts` in the blueprint, re-validate, regenerate.
- **Change the schema/fields:** edit `target_output_spec` in the blueprint, then hand-edit `poc/schemas/output_schema.py` to match (this pattern is `rag`, so `generate_schema.py`/SchemaGenerator is not used — the schema was hand-authored, see Phase 4 skip rule).
- **Tune a component option:** set it in `workflow.steps[].parameters` in the blueprint, then mirror the change into the corresponding constructor call in `run_poc.py` (e.g. `retriever_top_k`, `NOT_FOUND_FLOOR`).

## Configuration
- **Model provider:** azure_openai
- **Model preferences:** generation_model: gpt-5.4, temperature: 1.0, reasoning_effort: medium, embedding_model: Azure OpenAI embedding deployment supported by RAGWorkflow; exact deployment name is an environment setting
- **Integration targets:** _none_

## Tests and evaluation
- Evaluation requirements: Deterministic acceptance test using the four supplied role-tagged queries (Q01-Q04), checked against required facts, the exact access decision (allowed/denied), and required citation pairs per query. No numerical RAG-quality threshold (e.g. a fixed recall/precision score) was specified for the first PoC.
- See `evals/` for the basic evaluation script and `evaluation_plan.md` for the full plan.

**Gotchas for future developers:**
- `VisionRagParser.convert_doc_to_chunks_with_vision()` strips the file extension from `document_name` unless you pass it explicitly — always pass the full filename (`employee_travel_policy.pdf`), or citations will silently lose the `.pdf` suffix.
- Chroma metadata filters (`Retriever.search(filters=...)`) are exact-equality only, ANDed across keys — no "list contains" operator. That is why access control is modeled as one boolean `role_<role>` field per role rather than storing `allowed_roles` as a list.
- `AnswerGenerator.generate()` hardcodes `temperature=0.0` and has no override — do not switch answer generation back to it without also dropping the `temperature=1.0` requirement, or re-implement via a direct client call as done here.
- `NOT_FOUND_FLOOR` and the restricted-topic comparison in `classify_and_answer()` are heuristics tuned for this fixture's score distribution; if real documents/queries produce very different similarity scores, re-tune during Gate 3 rather than trusting the default blindly.
- The Chroma store at `poc/chroma_store/` is deleted and rebuilt on every run for repeatability — remove that `shutil.rmtree()` call if you want incremental indexing across runs.
