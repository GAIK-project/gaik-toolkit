# UC02 wizard-requirement coverage

This matrix audits the UC02 scripted interaction against the GAIK Solution Wizard at commit `79586c93ea3286f68acf3ad3810a370c4295fa01`.

| Requirement area | Covered by |
|---|---|
| `phase_1.output_directory` | scripted_answers.json#run_setup |
| `phase_1.use_case_description` | initial_prompt.txt |
| `business_spec.current_process` | SA01 |
| `business_spec.pain_points` | SA01 |
| `business_spec.proposed_solution` | initial_prompt.txt; SA01 |
| `business_spec.intended_users` | SA01 |
| `business_spec.reviewers` | SA01; SA05 |
| `business_spec.stakeholders` | SA01; SA05 |
| `business_spec.input_artifacts` | initial_prompt.txt; SA02 |
| `business_spec.target_outputs` | initial_prompt.txt; SA03; SA07 |
| `business_spec.success_criteria` | SA07; SA09 |
| `business_spec.expected_value` | SA01; SA09 |
| `business_spec.risks` | SA09 |
| `business_spec.poc_goal` | SA07 |
| `technical_spec.input_types` | SA02 |
| `technical_spec.input_formats` | SA02 |
| `technical_spec.output_types` | SA03; SA07 |
| `technical_spec.language` | SA02 |
| `technical_spec.domain_vocabulary` | SA10 |
| `technical_spec.data_sources` | SA02 |
| `technical_spec.model_provider` | SA08 |
| `technical_spec.model_preferences` | SA08 |
| `technical_spec.security_constraints` | SA06 |
| `technical_spec.integration_targets` | SA05 |
| `technical_spec.human_review` | SA04; SA05 |
| `technical_spec.evaluation_requirements` | SA07 |
| `technical_spec.runtime_interface` | SA05 |
| `technical_spec.formatted_pdf_question` | SA07 |
| `target_output_spec.schema_name` | SA03 |
| `target_output_spec.fields` | SA03 |
| `target_output_spec.field_types` | SA03 |
| `target_output_spec.required_fields` | SA03; SA11 |
| `target_output_spec.optional_fields` | SA03 |
| `target_output_spec.field_descriptions` | SA03; semantic names |
| `target_output_spec.allowed_values` | SA03; SA10; SA11 |
| `target_output_spec.confidence_required` | SA04 |
| `target_output_spec.missing_value_policy` | SA03; SA04; SA11 |
| `target_output_spec.validation_rules` | SA11 |
| `business_process.participants` | SA01; SA05 |
| `business_process.external_parties` | SA01; SA05 |
| `business_process.manual_steps` | SA05 |
| `business_process.exceptions` | SA05 |
| `business_process.decision_points` | SA05 |

## Selection-relevant constraints

| Option or rule | Frozen value |
|---|---|
| `VisionExtractor.task` | Purchase-order extraction task |
| `VisionExtractor.schema_ref` | PurchaseOrderERPRecord schema or equivalent generated schema assets |
| `VisionExtractor.include_verification` | true |
| `single_extraction_path` | Use VisionExtractor without a second executable DocumentsToStructuredData or MultimodalParser-to-Extractor pipeline over the same input. |

One global `Yes. Proceed without changes.` policy covers all seven routine confirmations. The post-baseline recovery protocol permits a maximum of three refinements and never changes the original EQ4 result.
