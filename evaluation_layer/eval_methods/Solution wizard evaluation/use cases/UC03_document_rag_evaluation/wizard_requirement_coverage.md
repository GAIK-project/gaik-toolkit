# UC03 wizard requirement coverage

The fixed prompt and scripted answer sheet provide an answer source for every requirement field. One global Yes-without-changes policy covers routine confirmations; adaptive questions use the fixed fallback.

## phase_1

| Field | Source | Expected value | Status |
|---|---|---|---|
| output_directory | scripted_answers.json#run_setup |  | covered |
| use_case_description | initial_prompt.txt |  | covered |

## business_spec

| Field | Source | Expected value | Status |
|---|---|---|---|
| current_process | SA01 |  | covered |
| pain_points | SA01 |  | covered |
| proposed_solution | initial_prompt.txt; SA01 |  | covered |
| intended_users | SA01 |  | covered |
| reviewers | SA01; SA04 |  | covered |
| stakeholders | SA01; SA05 |  | covered |
| input_artifacts | initial_prompt.txt; SA02 |  | covered |
| target_outputs | initial_prompt.txt; SA03; SA07 |  | covered |
| success_criteria | SA07; SA09 |  | covered |
| expected_value | SA01; SA09 |  | covered |
| risks | SA09 |  | covered |
| poc_goal | SA07 |  | covered |

## technical_spec

| Field | Source | Expected value | Status |
|---|---|---|---|
| input_types | SA02 |  | covered |
| input_formats | SA02 |  | covered |
| output_types | SA03; SA07 |  | covered |
| language | SA02 |  | covered |
| domain_vocabulary | SA10 |  | covered |
| data_sources | SA02 |  | covered |
| model_provider | SA08 |  | covered |
| model_preferences | SA08 |  | covered |
| security_constraints | SA06 |  | covered |
| integration_targets | SA02; SA07 |  | covered |
| human_review | SA01; SA04; SA05 |  | covered |
| evaluation_requirements | SA07 |  | covered |
| runtime_interface | SA05 |  | covered |
| formatted_pdf_question | SA07 |  | covered |

## target_output_spec

| Field | Source | Expected value | Status |
|---|---|---|---|
| schema_name | SA03 |  | covered |
| fields | SA03 |  | covered |
| field_types | SA03 |  | covered |
| required_fields | SA03; SA11 |  | covered |
| optional_fields | SA03 |  | covered |
| field_descriptions | SA03; semantic names |  | covered |
| allowed_values | SA03; SA11 |  | covered |
| confidence_required | Not included by the UC03 scenario design | No corresponding output field is requested. | covered |
| missing_value_policy | SA04; SA11 |  | covered |
| validation_rules | SA11 |  | covered |

## business_process

| Field | Source | Expected value | Status |
|---|---|---|---|
| participants | SA01; SA05 |  | covered |
| external_parties | SA01 |  | covered |
| manual_steps | SA05 |  | covered |
| exceptions | SA04; SA05; SA06 |  | covered |
| decision_points | SA05; SA06 |  | covered |

## selection_relevant_options

| Field | Source | Expected value | Status |
|---|---|---|---|
| RAG-Workflow.document_parser | SA02; SA10; GAIK registry | Parse PDFs into structure-aware chunks with source and access metadata | covered |
| RAG-Workflow.retriever.top_k | SA10 | 4 | covered |
| RAG-Workflow.retriever.metadata_filter | SA06; SA10 | allowed_roles filter before retrieval | covered |
| RAG-Workflow.answer_generator.citations | SA03; SA04; SA11 | True | covered |
| single_rag_path | GAIK registry; EQ2-C02 | Use the RAG-Workflow module without duplicating a second executable parser/embedder/retriever/generator pipeline over the same collection. | covered |

## Confirmation and recovery

Seven routine confirmations use the single fixed response `Yes. Proceed without changes.` Recovery permits at most three refinements and never changes the attempt-0 EQ4 result.

## Unexpected questions

Not specified for this evaluation. If a value is required, record it as an explicit assumption for user confirmation.
