# UC03 scripted answers

Use `initial_prompt.txt` verbatim. Provide an answer only when the wizard asks a matching question. For every routine confirmation, answer **Yes. Proceed without changes.**

## SA01 - business_context_and_stakeholders

**Trigger:** Who uses the solution, what is the current process, what problem should be solved, or who else is involved?

**Answer:** Employees are the main users. Today they search internal policies, manuals, and management documents manually, which is slow and can lead to incomplete or unsupported answers. Knowledge owners maintain the source documents, managers can access management-confidential material, and ordinary employees cannot. The expected value is faster access to reliable internal knowledge with traceable sources and enforced access boundaries. No human reviewer is required for every answer.

**Supports:** EQ1-R01, EQ1-R02, EQ1-R03, EQ1-R04, EQ1-R05, EQ1-R34

## SA02 - document_collection_inputs_and_language

**Trigger:** What documents, formats, languages, repositories, metadata, or document-quality conditions must be supported?

**Answer:** The evaluated collection contains three synthetic, text-based English PDFs supplied in the wizard-visible input bundle: `employee_travel_policy.pdf`, `mx200_maintenance_manual.pdf`, and the management-confidential `project_aurora_pricing_strategy.pdf`. The same bundle contains `access_manifest.json`, `query_set.json`, and `poc_input_bundle.json`. Each document has a title, filename, classification, allowed-role metadata, and 1-based PDF page-number metadata. The first PoC uses these supplied local inputs; connection to a live document repository is outside its scope.

**Supports:** EQ1-R06, EQ1-R07, EQ1-R08, EQ1-R28, EQ2-C03

## SA03 - rag_answer_record_and_citations

**Trigger:** What output, answer schema, fields, field types, citations, required fields, optional fields, or allowed values should be returned?

**Answer:** Use a RAGAnswerRecord or equivalent JSON structure. Required fields are `query_id` (string), `role` (`employee` or `manager`), `question` (string), `access_decision` (`allowed` or `denied`), `answer` (string), and `citations` (list). Each citation must be a two-element list in the exact format `[file_name, page_number]`, where `file_name` is a string and `page_number` is a 1-based integer. `refusal_reason` is required when `access_decision` is `denied` and may otherwise be null. Authorized factual answers require at least one supporting citation. Denied answers require an empty citations list and must not reveal restricted content.

**Supports:** EQ1-R09, EQ1-R10, EQ1-R11, EQ1-R12, EQ1-R13, EQ1-R14, EQ1-R15, EQ1-R16, EQ1-R17, EQ1-R18, EQ1-R19, EQ1-R20, EQ1-R39, EQ2-C08

## SA04 - grounding_uncertainty_and_no_answer_policy

**Trigger:** How should grounding, uncertainty, missing evidence, conflicting information, or unanswerable questions be handled?

**Answer:** Answers must use only retrieved content that the user's role is allowed to access. Cite every material factual claim using `[file_name, page_number]`. If the authorized sources do not support an answer, state that the information was not found and do not speculate. If sources conflict, identify the conflict and cite both sources. Do not fabricate citations. A per-answer human reviewer is not required.

**Supports:** EQ1-R21, EQ1-R22, EQ1-R23, EQ1-R24, EQ1-R27, EQ2-C06

## SA05 - employee_interaction_and_business_process

**Trigger:** How will employees interact with the system, how are questions submitted, how are answers and citations presented, and what happens after an answer?

**Answer:** In the final production-ready version (not the PoC), employees use a web application. They sign in, enter a natural-language question, and receive an answer with clickable citations showing the source filename and 1-based PDF page number. The application uses the employee's assigned role when filtering documents. Employees may open a cited source only when their role permits access. There is no routine approve-or-return review cycle for each answer. The first PoC may use a command-line interface and JSON output instead of the web application.

**Supports:** EQ1-R25, EQ1-R26, EQ1-R27, EQ1-R40, EQ2-C07, EQ2-C09

## SA06 - security_access_storage_and_audit

**Trigger:** What privacy, security, role, access-control, storage, retention, authentication, audit, or data-residency requirements apply?

**Answer:** The travel policy and maintenance manual are available to employee and manager roles. The Project Aurora strategy is management-confidential and available only to the manager role. Access filtering must happen before retrieval so unauthorized chunks never enter the model context. An unauthorized answer must refuse without exposing restricted facts or citations. External model APIs are allowed. The synthetic fixtures contain no personal data. The PoC may use a local vector store and simulated role values; enterprise identity integration and a full audit-log service are outside PoC scope. No exact retention period is specified.

**Supports:** EQ1-R28, EQ1-R29, EQ1-R30, EQ1-R31, EQ1-R32, EQ1-R41, EQ1-R42, EQ2-C05

## SA07 - poc_goal_interface_and_evaluation

**Trigger:** What should the first proof-of-concept demonstrate, what interface should it use, what fixture should it process, or what acceptance criteria should apply?

**Answer:** The first PoC should demonstrate role-aware, citation-grounded question answering over the three PDFs, `access_manifest.json`, and `query_set.json` supplied in the wizard-visible input bundle. It must support the command `python run_poc.py --input <path-to-poc_input_bundle.json>`, resolve the other supplied files relative to that bundle, execute all four role-tagged queries, and save non-empty parseable JSON results. The role is trusted request metadata and must not be inferred from the question. Q01 uses role `employee` and asks the Helsinki hotel limit; it must answer EUR 180 per night and written Finance Director approval before booking when exceeded, citing `["employee_travel_policy.pdf", 3]`. Q02 uses role `employee` and asks about the MX-200 filter; it must answer inspection every 250 operating hours and replacement after 1,000 operating hours or above 1.8 bar, whichever occurs first, citing `["mx200_maintenance_manual.pdf", 3]` and `["mx200_maintenance_manual.pdf", 4]`. Q03 uses role `employee` and asks for the Project Aurora discount ceiling; it must return `access_decision` `denied`, an empty citations list, and no 12 percent, 22 percent, or Chief Financial Officer details. Q04 uses role `manager` and asks for the Project Aurora ceiling and exception approver; it must answer 12 percent and written Chief Financial Officer approval above the ceiling, citing `["project_aurora_pricing_strategy.pdf", 3]`. A web interface, live repository connector, enterprise sign-in, and numerical RAG-quality threshold are outside the first PoC.

**Supports:** EQ1-R33, EQ1-R35, EQ1-R38, EQ4-X01, EQ4-X02, EQ4-X03, EQ4-X04

## SA08 - provider_model_scale_and_budget

**Trigger:** Which provider, model, embedding model, temperature, deployment topology, SLA, throughput, volume, or budget should be used?

**Answer:** Use Azure OpenAI for generation with model gpt-5.4, temperature 1.0, and reasoning effort medium. Use an Azure OpenAI embedding model supported by the selected GAIK RAG workflow; the exact embedding deployment name is an environment setting. No SLA, throughput, document-volume, latency, or budget target is specified. Valid implementation defaults may be recorded as assumptions, not user-confirmed requirements.

**Supports:** EQ1-R36, EQ1-D01, EQ1-D03, EQ2-C04

## SA09 - business_success_and_risks

**Trigger:** What does business success mean, is there a quantified target, and what risks should be considered?

**Answer:** Business success means employees find reliable answers faster, can verify them through citations, and never receive content outside their role. No numerical time-saving, answer-accuracy, cost, or adoption target is specified. Key risks are hallucinated answers, fabricated or wrong citations, retrieval of restricted chunks, leakage through answer text or citations, stale documents, and returning an answer when the authorized collection contains no support.

**Supports:** EQ1-R05, EQ1-R35, EQ1-R37

## SA10 - retrieval_chunking_and_domain_terms

**Trigger:** What retrieval, chunking, ranking, metadata, vocabulary, identifier, or citation conventions should apply?

**Answer:** Preserve `file_name`, 1-based integer `page_number`, `classification`, and `allowed_roles` metadata on every chunk. Use structure-aware chunking with moderate overlap. Retrieve the top four eligible chunks using semantic similarity; hybrid search or reranking may be added but is not required. Apply the role filter before similarity retrieval. Generate citations only as `[file_name, page_number]`. Preserve exact values and units such as EUR 180, 250 operating hours, 1,000 operating hours, 1.8 bar, 12 percent, and 22 percent.

**Supports:** EQ1-R08, EQ1-R16, EQ1-R17, EQ1-R41, EQ2-C04, EQ2-C05

## SA11 - validation_rules

**Trigger:** What validation rules or special instructions should apply to answers, citations, access decisions, and refusals?

**Answer:** Every output must preserve `query_id` and `role`. `access_decision` must be `allowed` or `denied`. An allowed factual answer requires at least one citation to a document allowed for that role. Each citation must contain exactly two elements in the order `[file_name, page_number]`, with a string filename and a 1-based integer page number. A denied answer requires a `refusal_reason`, an empty citations list, and no restricted facts. Do not answer from model memory when authorized evidence is absent. The four PoC results must be returned separately and must match the expected access behavior and citation pairs.

**Supports:** EQ1-R10, EQ1-R12, EQ1-R15, EQ1-R18, EQ1-R19, EQ1-R20, EQ1-R21, EQ1-R22, EQ1-R23, EQ1-R39, EQ1-R42, EQ2-C06, EQ2-C08

## Unexpected questions

Not specified for this evaluation. If a value is required, record it as an explicit assumption for user confirmation.

## Recovery

Only if the original PoC fails, return its recorded execution evidence to the wizard. Allow at most three sequential refinements. Stop after success. Recovery never changes EQ4.
