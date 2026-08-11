# UC01 scripted answer sheet

Use this sheet in both `run_01` and `run_02`. It covers every requirement field and planned confirmation question defined by the Solution Wizard skill at commit `79586c93ea3286f68acf3ad3810a370c4295fa01`.

## Run setup

The wizard skill normally asks for the output directory before it asks for the use-case description.

| Run | Output folder inside this package |
|---|---|
| Run 1 | `runs/run_01/generated_package` |
| Run 2 | `runs/run_02/generated_package` |

Select the corresponding folder when the wizard asks where to write its output. If the interface requires an absolute path, use the operating system's **Copy as path** action on that folder. If the interface uses its own workspace, copy the complete, unmodified wizard output into the corresponding `generated_package/` folder after the run. Do not enter or record this path in `run_metadata.json`.

When the wizard asks for the use-case description, send `initial_prompt.txt` verbatim.

Give an answer only when the wizard asks about the corresponding topic. Do not volunteer all answers at once.

## Fixed requirement answers

| ID | When the wizard asks about… | Fixed answer |
|---|---|---|
| SA01 | Users, reviewers, stakeholders, current process, proposed solution, or expected value | Field technicians create the voice reports and are the intended users. A maintenance supervisor reviews the generated ticket. Today the technicians type the same information manually into the maintenance management system. The proposed solution converts their voice messages into structured maintenance tickets. The main expected value is faster reporting with fewer missing details. No additional business stakeholder is required for the PoC. |
| SA02 | Input type or format, language, duration, data source, output language, or speakers | The source is a voice message recorded or uploaded by a field technician. The input language is Finnish and the file is in a common audio format such as WAV or M4A. A typical message is under two minutes and has one speaker, so speaker diarization is not needed. Extracted free-text values remain in Finnish. The JSON field names and canonical urgency labels use English. |
| SA03 | Schema name, fields, field types, required or optional fields, formats, or allowed values | Use the schema name `MaintenanceTicket`. It contains `reporter_name` (`str`, optional), `asset_identifier` (`str`, optional), `location` (`str`, required), `fault_description` (`str`, required), `urgency` (`str`, required; `low`, `medium`, or `high`), `observation_date` (`date`, optional; `YYYY-MM-DD`), `observation_time` (`str`, optional; `HH:MM`), `actions_taken` (`list[str]`, optional), and `uncertain_fields` (`list[str]`, optional). A required field may still have a null or unknown value when it was not stated, but it must be flagged rather than invented. |
| SA04 | Missing, ambiguous, low-confidence, or uncertain information and review evidence | Leave an unstated value null or explicitly unknown and include the corresponding field name in `uncertain_fields`. Do not infer or fabricate a value. The supervisor must receive the structured ticket, uncertainty information, and the audio transcript. A numerical confidence score is not required. Component-supplied confidence information may be included as supplementary evidence. |
| SA05 | Review, approval, rejection, integration, external parties, or other business decisions | The supervisor reviews the structured ticket, uncertainty information, and transcript. The supervisor either approves the ticket or returns it to the field technician for correction and resubmission. Only an approved ticket may be transferred to the maintenance management system. For the PoC, save the approved ticket as JSON; a live API is outside scope. The input comes from an internal field technician, not an external party. There are no branch decisions beyond approve or return for correction. |
| SA06 | Privacy, security, access, storage, retention, audit, or data residency | The audio may contain an employee name and internal facility details. External model APIs are allowed, and local-only processing is not required. No provider-specific data-residency requirement is specified. The PoC must not retain raw audio after processing. The approved ticket and supervisor approval decision may be retained, but no exact retention period is specified. Authentication, production role-based access control, and a full audit-log implementation are outside the PoC scope; retaining the approval decision is sufficient. |
| SA07 | Interface, output formats, PoC goal, test data, evaluation metrics, thresholds, or acceptance | A command-line PoC is sufficient. Its final machine-readable output is a JSON maintenance ticket. The transcript and uncertainty information are review evidence; no PDF, HTML, or DOCX report is required. The PoC must accept the supplied Finnish audio fixture, exit successfully, produce a non-empty parseable JSON ticket, preserve the fixture facts, include required fields, and leave unsupported values null or unknown. Evaluate JSON parsing, required-field coverage, semantic fixture-fact matching, and unsupported-value introduction. No numerical accuracy threshold is specified for this single-fixture PoC. |
| SA08 | Provider, model, temperature, transcription model, topology, SLA, throughput, volume, or budget | The provider should be Azure OpenAI. Model=gpt5.4, temperature=0, transcription model=gpt-4o-transcribe. No deployment topology, SLA, throughput, volume, or budget is specified. A valid implementation default is acceptable, but it must not be presented as a user-confirmed requirement. |
| SA09 | Business success, quantified value, or risks | Business success means faster incident reporting with fewer missing details and a supervisor-verifiable ticket before transfer. No numerical time-saving, accuracy, or cost-saving target is specified. The main risks are Finnish transcription errors, incorrect asset, location, fault, or urgency values, unsupported values being introduced, and transfer without supervisor approval. |
| SA10 | Domain vocabulary, abbreviations, names, room codes, or equipment identifiers | Reports may contain Finnish facility names and alphanumeric room, asset, or equipment identifiers such as `P-17` or `B2`. Preserve identifiers exactly as stated. No fixed domain glossary is supplied. The urgency controlled list is `low`, `medium`, and `high`. |
| SA11 | Validation rules or special extraction instructions | The ticket must contain the `location`, `fault_description`, and `urgency` keys. Urgency must be `low`, `medium`, or `high` when known. `observation_date` uses `YYYY-MM-DD` and `observation_time` uses `HH:MM` when present. Values must be grounded in the voice message. Missing or uncertain values remain null or unknown and are identified in `uncertain_fields`. |

## Global confirmation policy

At every routine wizard confirmation before the original PoC is executed, answer:

> Yes. Proceed without changes.

Do not correct the specification, field list, extraction prompt, schema, component selection, workflow, or PoC scaffold. This single policy replaces separate gate-specific answers.

## Recovery policy

First execute the original, unmodified PoC and retain that result for EQ4. If it fails to execute successfully, return its recorded execution evidence to the wizard and allow at most three refinement attempts. Do not provide corrective code or new requirements. Execute the PoC after each refinement and stop after the first success or the third unsuccessful refinement.

Record:

- `0` when the original PoC succeeds;
- `1`, `2`, or `3` when it succeeds after that many refinements;
- `N/A` when it is still unsuccessful after three refinements.

Refined executions are a recovery diagnostic and never replace the original EQ4 result.

## Unanticipated questions

If the wizard asks a question not covered above, respond exactly:

> Not specified for this evaluation. If a value is required, record it as an explicit assumption for user confirmation.

Do not invent an answer for the sake of completing the wizard.
