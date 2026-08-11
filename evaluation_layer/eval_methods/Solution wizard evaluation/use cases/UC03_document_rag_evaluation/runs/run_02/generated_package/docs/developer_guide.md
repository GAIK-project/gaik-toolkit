# Developer Guide — Manufacturing Internal Knowledge Assistant

> Package structure, extension points, component configuration, tests, and evaluation.

## Architecture
This use case is driven by an **executable JSON blueprint** (`use_case.blueprint.json`) — the single source of truth. The PoC, the visual workflows (`workflow.mmd`, `workflow.bpmn`), and these docs are all *generated from it*. To change behaviour, edit the blueprint and regenerate; never hand-edit generated artifacts.

## Pipeline
| Step | Type | Component | Inputs | Outputs |
|------|------|-----------|--------|---------|
| load_input_bundle | user_task | — <br/>opts: entrypoint_flag=--input, description=User provides path to poc_input_bundle.json via CLI. All referenced files (PDFs, access_manifest.json, query_set.json) are resolved relative to the bundle file. | — | poc_input_bundle, document_collection, access_manifest, query_set |
| run_rag_pipeline | automated_task | RAGWorkflow <br/>opts: collection_name=manufacturing_knowledge, citations=True, conversation_history=False, stream=False, retriever_top_k=4, persist=True, rbac_metadata_fields=['classification', 'allowed_roles', 'file_name', 'page_number'], chunking_strategy=structure_aware, chunk_overlap=moderate, role_filter_field=allowed_roles, role_source=query_metadata, deny_when_no_allowed_chunks=True, citation_format=[file_name, page_number], citation_page_type=1-based integer, preserve_exact_values=True, no_speculation=True | document_collection, access_manifest, query_set | answer_records |
| save_results | automated_task | — <br/>opts: output_file=output/results.json, format=json_array | answer_records | saved_results |

### Components and their options
- **RAGWorkflow** (module) — Use case is document Q&A with citations over a local document collection. RAGWorkflow covers the full indexing (chunking, embedding, storage) and retrieval-augmented generation pipeline. Citations are required and enabled. RBAC metadata filtering is implemented at the PoC level using the Chroma store metadata filter on allowed_roles.

**RAGWorkflow constructor** (wired in `poc/run_poc.py`):

| Parameter | Value | Source |
|---|---|---|
| `use_azure` | `True` | `config.yaml` → `use_azure` |
| `persist` | `True` | hard-coded (PoC always persists) |
| `persist_path` | `poc/output/chroma_store/` | computed at runtime; deleted and recreated on each run |
| `collection_name` | `"manufacturing_knowledge"` | hard-coded constant |
| `citations` | `True` | explicit requirement |
| `conversation_history` | `False` | batch CLI — no multi-turn context needed |
| `stream` | `False` | batch pipeline — streaming irrelevant |
| `retriever_top_k` | `4` | user-specified: "top four eligible chunks" |

Model credentials are read from environment variables (`AZURE_API_KEY`, `AZURE_ENDPOINT`, `AZURE_API_VERSION`, `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`) via `.env` / `python-dotenv`.

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
- **Model preferences:** generation_model: gpt-5.4, temperature: 1.0, reasoning_effort: medium, embedding_model: ${AZURE_OPENAI_EMBEDDING_DEPLOYMENT}
- **Integration targets:** _none_

## Tests and evaluation
- Evaluation requirements: Four role-tagged queries (Q01-Q04) with exact expected access decisions, answer content, and citation pairs. Q01 (employee, Helsinki hotel limit): access=allowed, EUR 180/night + Finance Director approval, cite [employee_travel_policy.pdf, 3]. Q02 (employee, MX-200 filter): access=allowed, 250h inspection + 1000h or 1.8bar replacement, cite [mx200_maintenance_manual.pdf, 3] and [mx200_maintenance_manual.pdf, 4]. Q03 (employee, Project Aurora ceiling): access=denied, empty citations, no 12%/22%/CFO details. Q04 (manager, Project Aurora ceiling and approver): access=allowed, 12% ceiling + CFO written approval, cite [project_aurora_pricing_strategy.pdf, 3].
- See `evals/` for the basic evaluation script and `evaluation_plan.md` for the full plan.

**RBAC implementation note:** `RAGWorkflow.index_documents()` does not accept custom per-document metadata. The RBAC filter relies on the `document_name` field that RAGWorkflow writes automatically from the `filenames` parameter. Always pass `filenames=[<basename>, ...]` when indexing so the filter keys match the basenames in `access_manifest.json`. Never pass full file paths as filenames — the Chroma `where` filter will not match.

**Two-phase access detection:** For each query, `run_poc.py` first queries the full (unfiltered) index to detect whether any top-k result is from a restricted document. Only then does it query the role-filtered index. This means two embedding calls per query for the RBAC-detection path. For larger deployments, consider caching the full-collection result or pre-classifying queries by topic.

**Chroma store reset:** The store is deleted and recreated at the start of every run (`shutil.rmtree`). This prevents duplicate chunks on repeated runs but means indexing runs on every execution. For large document collections, persist the store between runs and only re-index when documents change.

**`reasoning_effort: medium`** is recorded in the blueprint and `config.yaml` but is not currently passed to the Azure OpenAI API via the RAGWorkflow constructor (no `reasoning_effort` parameter exposed). To enable it, access the underlying chat-completion config via `RAGWorkflow`'s `api_config` parameter once support is added to GAIK, or post-process results accordingly.

**Citation page numbers:** `RAGWorkflow` stores `page_number` from its `VisionRagParser`. These are 1-based integers matching the PDF page layout. If a document's parser returns `"Unknown"` for a page number (e.g. a malformed PDF), the PoC defaults to `1`. Verify page metadata for any new document before using it in production.
