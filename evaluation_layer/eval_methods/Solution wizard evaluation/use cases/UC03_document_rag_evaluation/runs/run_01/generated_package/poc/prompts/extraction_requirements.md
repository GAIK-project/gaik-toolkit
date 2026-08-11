Extract the following fields from the provided content.

If a field cannot be determined, apply this policy: If authorized sources do not support an answer, state the information was not found and do not speculate. Do not fabricate citations.

1. query_id (str, REQUIRED): Unique query identifier from query_set.json
2. role (str, REQUIRED): Requestor role from trusted request metadata; must not be inferred from question content -- allowed values: employee, manager
3. question (str, REQUIRED): The natural-language question as supplied in query_set.json
4. access_decision (str, REQUIRED): allowed if the role has access to documents that answer the query; denied otherwise -- allowed values: allowed, denied
5. answer (str, REQUIRED): Cited factual answer grounded only in retrieved content; refusal message when access_decision=denied
6. citations (list, REQUIRED): List of [file_name, page_number] pairs (1-based integer); empty list when access_decision=denied
7. refusal_reason (str, OPTIONAL): Required (non-null) when access_decision=denied; must not reveal restricted facts; null otherwise