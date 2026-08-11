# Evidence-extraction prompt contract

The optional LLM step aligns semantically equivalent wizard wording with oracle checks. It is an evidence finder, not the evaluator.

For every check, return:

- `check_id`
- `generated_value`, or `NOT FOUND`
- `evidence` with an exact source file and JSON path, conversation line, command result, or file excerpt

The LLM must not return a Yes/No/pass/fail verdict. A missing requirement remains a row: `generated_value` is `NOT FOUND`, evidence states what was searched, and the human evaluator enters `No`. The final verdict is always entered by a human in the comparison workbook.
