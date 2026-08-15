# UC05 Scripted Answers

Use an answer only when the wizard asks a question covered by its trigger. Do not volunteer a scripted answer if the wizard never asks for it. For an uncovered question, answer: **Not specified for this evaluation. If a value is required, record it as an explicit assumption for user confirmation.** At routine confirmation gates, answer: **Yes. Proceed without changes.**

## SA01 - Users, current process, and problem

**Trigger:** Who performs the work today, who will use or review the output, and what problem should be addressed?

**Answer:** A project coordinator currently listens to the meeting recording, checks the agenda and participant list, and manually prepares the record. Project team members use the approved record. A project manager reviews and approves it. The main problems are the time required, inconsistent action tracking, and difficulty tracing decisions back to their sources.

## SA02 - Business objective and success

**Trigger:** What business outcome or success criteria are expected?

**Answer:** The solution should reduce manual preparation while producing a reviewable record that clearly separates agenda topics, discussion summaries, decisions, assigned actions, unresolved issues, and conflicts. Success means that supported decisions and actions are captured accurately with evidence, while missing owners, dates, or decisions are not invented.

## SA03 - Inputs and language

**Trigger:** What inputs, formats, language, or input combination should the solution support?

**Answer:** Each meeting is supplied as one bundle containing an English WAV recording, a PDF agenda, and a JSON participant list. All three belong to the same meeting and must be processed together. The participant list contains the known names and roles and should be used to normalize speaker and owner names.

## SA04 - Target output schema

**Trigger:** What structured output and fields are required?

**Answer:** Return one JSON object with meeting_id, title, meeting_date, start_time, end_time, participants, topics, decisions, action_items, unresolved_issues, conflicts, and review_status. Each participant contains name and role. Each topic contains title and discussion_summary. Each decision contains decision_id, statement, and citations. Each action contains action_id, description, owner, due_date, uncertainty_reason, and citations. Owner and due_date are nullable when not explicitly stated. Each unresolved issue and conflict contains a description and citations. review_status should initially be pending_review.

## SA05 - Provenance, uncertainty, and conflicts

**Trigger:** How should evidence, uncertainty, conflicting sources, or unsupported information be handled?

**Answer:** Every decision, action, unresolved issue, and conflict must have at least one citation. Each citation is a single pipe-delimited string, and an item may carry several. For audio, use `file_name|start_timestamp|end_timestamp` with `HH:MM:SS` timestamps. For the agenda, use `file_name|page_number`. The spoken meeting determines what was actually decided; an agenda item is only planned content and must not be treated as a decision by itself. When sources conflict, record the conflict and follow the explicit spoken decision. Do not infer owners, deadlines, approvals, budgets, or facts that are not stated. Use `null` with `uncertainty_reason` when an action lacks an explicit owner or due date.

## SA06 - Human review and return path

**Trigger:** Who reviews the AI output, where does review occur, and what happens when it is returned?

**Answer:** The project manager reviews the generated record before it is accepted. The manager can approve it or return it to the project coordinator. On return, the coordinator can correct the record or upload corrected source material, after which processing and review repeat. The AI output must not be treated as approved before this review.

## SA07 - Employee interaction

**Trigger:** How should employees interact with the intended solution?

**Answer:** Use a web application. The project coordinator uploads the WAV recording, PDF agenda, and JSON participant list together, starts processing, reviews the generated fields, and downloads the record as JSON. The project manager uses the same application to approve or return the record.

## SA08 - Boundaries, security, and integration

**Trigger:** What security, retention, integration, provider, or deployment constraints apply?

**Answer:** The meeting material is internal. Access should be limited to the project team and designated reviewer. No connection to calendar, project-management, document-management, or identity systems is required in this evaluation. Choose a local whisper model for transcription, and an Azure model for extraction. The deployment platform, authentication method, and retention period are not specified. If values are needed, record them as assumptions for confirmation.

## SA09 - Scale and operational expectations

**Trigger:** What scale, performance, availability, or service-level requirements apply?

**Answer:** Not specified for this evaluation. The first version only needs to process one meeting bundle at a time. Do not invent an SLA, throughput target, concurrency level, or availability commitment.

## SA10 - PoC goal, interface, and evaluation

**Trigger:** What should the first proof of concept demonstrate, what interface should it use, what fixture should it process, and what acceptance criteria apply?

**Answer:** The first PoC should process the supplied `fixtures/poc_input_bundle.json`, which references the meeting WAV, agenda PDF, and participant JSON that will be provided with the PoC task. A command-line interface is sufficient and should accept `--input` followed by the bundle path. It must exit successfully and save non-empty parseable JSON. The output must capture the frozen meeting decisions, actions, unresolved issues, and date conflict; cite audio with the single string `file_name|start_timestamp|end_timestamp` using `HH:MM:SS` timestamps and the agenda with `file_name|page_number`; leave unsupported owners, dates, budget approval, and SSO decisions unset; and use `pending_review`. Compare the output semantically with `fixtures/expected_meeting_record.json`. The PoC must save its final JSON output inside the poc/output/ directory. The web application, authentication, external integrations, and operational scaling are outside the first PoC.
