# Wizard requirement-collection coverage

This matrix audits the UC01 scripted interaction against the GAIK Solution Wizard at commit `79586c93ea3286f68acf3ad3810a370c4295fa01`, using:

- `implementation_layer/solution_wizard/SKILL.md`;
- `implementation_layer/solution_wizard/src/solution_wizard/requirements.py`;
- the Audio-to-Structured-Data registry entry and reference card.

The audit checks whether the evaluator has a fixed source for every possible requirement category and planned confirmation question. It does not require the wizard to ask every question. If information is already present in the initial prompt or an earlier answer, the wizard may skip a follow-up.

## Phase 1

| Wizard item | Fixed source |
|---|---|
| Output directory | `scripted_answers.json` → `run_setup` |
| Use-case description | `initial_prompt.txt` |

## Business specification

| Wizard field | Fixed source |
|---|---|
| `current_process`, `pain_points`, `proposed_solution` | SA01 |
| `intended_users`, `reviewers`, `stakeholders` | SA01 and SA05 |
| `input_artifacts` | Initial prompt and SA02 |
| `target_outputs` | Initial prompt, SA03, and SA07 |
| `success_criteria`, `expected_value` | SA01, SA07, and SA09 |
| `risks` | SA09 |
| `poc_goal` | SA07 |

## Technical specification

| Wizard field | Fixed source |
|---|---|
| `input_types`, `input_formats`, `data_sources`, `language` | SA02 |
| `output_types` and formatted-PDF decision | SA03 and SA07 |
| `domain_vocabulary` | SA10 |
| `model_provider`, `model_preferences` | SA08 |
| `security_constraints` | SA06 |
| `integration_targets` | SA05 |
| `human_review` | SA04 and SA05 |
| `evaluation_requirements`, `runtime_interface` | SA07 |

## Target-output specification

| Wizard field | Fixed source |
|---|---|
| `schema_name`, `fields`, `field_types` | SA03 |
| `required_fields`, `optional_fields` | SA03 and SA11 |
| `field_descriptions` | SA03 and the semantically explicit field names |
| `allowed_values` | SA03, SA10, and SA11 |
| `confidence_required` | SA04 |
| `missing_value_policy` | SA03, SA04, and SA11 |
| `validation_rules` | SA11 |

## Optional business-process detail

| Wizard field | Fixed source |
|---|---|
| `participants` | SA01 and SA05 |
| `external_parties` | SA05 |
| `manual_steps`, `exceptions`, `decision_points` | SA05 |

## Component-option questions

| Selection-relevant option | Fixed answer |
|---|---|
| Transcription language | `fi` (SA02) |
| Finnish transcript enhancement | enabled, because the GAIK reference card defines enhanced transcription for Finnish |
| Speaker diarization | disabled (SA02) |
| Module subsumption | use `AudioToStructuredData` without a second executable pipeline containing its subsumed components |

Any other component-specific question caused by an unexpected alternative selection uses the fixed fallback answer. This prevents a new user preference from being introduced after the oracle was frozen.

## Confirmation and recovery policy

One global response covers all routine confirmations concerning the specification, target fields, extraction prompt, generated schema and types, module or component selection, workflow and BPMN, and PoC scaffolding:

> Yes. Proceed without changes.

This avoids unnecessary gate-specific entries while preserving the no-correction protocol.

The original, unmodified PoC is evaluated under EQ4. Only when that PoC fails to execute successfully may its execution evidence be returned to the wizard. The recovery protocol allows at most three refinement attempts. It records `0`, `1`, `2`, `3`, or `N/A` and never overwrites the baseline EQ4 result.

## Important interpretation

The cited wizard implementation treats an explicit “unknown,” “none,” or “not specified” value as an answered field. Its completeness indicator therefore checks representation completeness, not substantive information completeness. The evaluation avoids ambiguity by recording these values explicitly and by using:

> Not specified for this evaluation. If a value is required, record it as an explicit assumption for user confirmation.

This fallback applies to adaptive questions whose exact wording cannot be enumerated in advance.
