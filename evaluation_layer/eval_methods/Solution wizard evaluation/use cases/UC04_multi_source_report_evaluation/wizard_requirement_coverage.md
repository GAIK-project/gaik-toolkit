# UC04 Wizard Requirement Coverage

Every source below points to the fixed initial prompt or `scripted_answers.json`.

## phase_1

| Field | Source | Status |
|---|---|---|
| output_directory | scripted_answers.json#run_setup | covered |
| use_case_description | initial_prompt.txt | covered |

## business_spec

| Field | Source | Status |
|---|---|---|
| current_process | scripted_answers.json#SA01 | covered |
| pain_points | scripted_answers.json#SA01 | covered |
| proposed_solution | initial_prompt.txt; SA01 | covered |
| intended_users | scripted_answers.json#SA01 | covered |
| reviewers | scripted_answers.json#SA01; SA05 | covered |
| stakeholders | scripted_answers.json#SA01; SA05 | covered |
| input_artifacts | scripted_answers.json#SA02 | covered |
| target_outputs | scripted_answers.json#SA03; SA07 | covered |
| success_criteria | scripted_answers.json#SA07; SA09 | covered |
| expected_value | scripted_answers.json#SA01; SA09 | covered |
| risks | scripted_answers.json#SA09 | covered |
| poc_goal | scripted_answers.json#SA07 | covered |

## technical_spec

| Field | Source | Status |
|---|---|---|
| input_types | scripted_answers.json#SA02 | covered |
| input_formats | scripted_answers.json#SA02 | covered |
| output_types | scripted_answers.json#SA03; SA07 | covered |
| language | scripted_answers.json#SA02; SA03 | covered |
| domain_vocabulary | scripted_answers.json#SA04; SA07 | covered |
| data_sources | scripted_answers.json#SA02 | covered |
| model_provider | scripted_answers.json#SA08 | covered |
| model_preferences | scripted_answers.json#SA08; SA10 | covered |
| security_constraints | scripted_answers.json#SA06 | covered |
| integration_targets | scripted_answers.json#SA02; SA06; SA07 | covered |
| human_review | scripted_answers.json#SA01; SA05; SA11 | covered |
| evaluation_requirements | scripted_answers.json#SA07; SA11 | covered |
| runtime_interface | scripted_answers.json#SA05; SA07 | covered |
| formatted_pdf_question | scripted_answers.json#SA07 | covered |

## target_output_spec

| Field | Source | Status |
|---|---|---|
| schema_name | scripted_answers.json#SA03 | covered |
| fields | scripted_answers.json#SA03 | covered |
| field_types | scripted_answers.json#SA03 | covered |
| required_fields | scripted_answers.json#SA03; SA11 | covered |
| optional_fields | scripted_answers.json#SA03 | covered |
| field_descriptions | scripted_answers.json#SA03 | covered |
| allowed_values | scripted_answers.json#SA03; SA11 | covered |
| confidence_required | scripted_answers.json#SA03: no confidence field requested | covered |
| missing_value_policy | scripted_answers.json#SA04 | covered |
| validation_rules | scripted_answers.json#SA04; SA11 | covered |

## business_process

| Field | Source | Status |
|---|---|---|
| participants | scripted_answers.json#SA01; SA05 | covered |
| external_parties | scripted_answers.json#SA01; SA06 | covered |
| manual_steps | scripted_answers.json#SA05 | covered |
| exceptions | scripted_answers.json#SA04; SA05 | covered |
| decision_points | scripted_answers.json#SA05; SA11 | covered |

## selection_relevant_options

| Field | Source | Status |
|---|---|---|
| MultiSourceReportGenerator.agentic | scripted_answers.json#SA10 | covered |
| MultiSourceReportGenerator.strict_review | scripted_answers.json#SA10 | covered |
| MultiSourceReportGenerator.parser_choice | scripted_answers.json#SA10 | covered |
| MultiSourceReportGenerator.sample_report_path | scripted_answers.json#SA02; scripted_answers.json#SA10 | covered |
| MultiSourceReportGenerator.include_source_references | scripted_answers.json#SA03; scripted_answers.json#SA10 | covered |
| MultiSourceReportGenerator.include_evidence_index | scripted_answers.json#SA03; scripted_answers.json#SA10 | covered |
| MultiSourceReportGenerator.output_docx | scripted_answers.json#SA07; scripted_answers.json#SA10 | covered |
| module_first_path | scripted_answers.json#SA10; GAIK registry | covered |

## Confirmation and recovery

Seven routine confirmation points use the single fixed response in `scripted_answers.json#confirmation_policy`. The original PoC is EQ4 baseline; at most three technical recovery refinements are allowed and are unscored.
