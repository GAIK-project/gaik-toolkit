# Manufacturing Internal Knowledge Assistant — Proof of Concept

Role-aware RAG assistant over internal manufacturing policies, equipment manuals,
and management documents.  Answers are grounded in citations; role-based access
control prevents management-confidential content from reaching unauthorised users.

---

## What this PoC demonstrates

| Scenario | Query | Role | Expected outcome |
|---|---|---|---|
| Q01 | Helsinki hotel limit and approval rule | employee | Allowed — EUR 180/night, Finance Director approval |
| Q02 | MX-200 filter inspection and replacement schedule | employee | Allowed — 250 h inspection, 1 000 h or 1.8 bar replacement |
| Q03 | Project Aurora discount ceiling | employee | **Denied** — management-confidential |
| Q04 | Project Aurora ceiling and exception approver | manager | Allowed — 12 % ceiling, CFO written approval |

Each result is a `RAGAnswerRecord` with `query_id`, `role`, `question`,
`access_decision`, `answer`, `citations` (`[file_name, page_number]` pairs),
and `refusal_reason` (populated only on denials).

---

## Prerequisites

- Python 3.11+
- GAIK toolkit with RAG extras: `pip install -r requirements.txt`
- Azure OpenAI credentials (see `.env.example`)

---

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure credentials
cp .env.example .env
# Edit .env:
#   AZURE_API_KEY               — your Azure OpenAI API key
#   AZURE_ENDPOINT              — https://your-resource.openai.azure.com/
#   AZURE_OPENAI_EMBEDDING_DEPLOYMENT — name of your embedding deployment
```

---

## Running the PoC

```bash
python run_poc.py --input <path-to-poc_input_bundle.json>
```

**Example** (using the supplied evaluation bundle):

```bash
python run_poc.py --input "C:\Users\h02317\Downloads\runs\run_02\wizard_input\poc_input_bundle.json"
```

The script:
1. Reads `poc_input_bundle.json` and resolves all referenced files relative to it.
2. Indexes the three PDFs into a local Chroma vector store (`output/chroma_store/`).
3. Processes all four queries with role-based access control.
4. Writes results to `output/results.json`.

---

## RBAC logic

For each query the pipeline applies a two-phase access check:

1. **Restricted-document detection** — the full index is queried (no role filter).
   If any top-4 result is from a document the query role cannot access, the
   query is denied immediately (no answer or citation is returned).

2. **Role-filtered retrieval** — if no restricted hits were detected, a Chroma
   `document_name` filter restricts retrieval to the role's authorised documents.
   The LLM then generates an answer grounded only in those chunks.

Role is taken directly from the query record and is never inferred from the
question text.

---

## Output format

`output/results.json` — a JSON array of `RAGAnswerRecord` objects:

```json
[
  {
    "query_id": "Q01",
    "role": "employee",
    "question": "What is the maximum reimbursable hotel rate in Helsinki ...",
    "access_decision": "allowed",
    "answer": "The maximum reimbursable hotel rate in Helsinki is EUR 180 ...",
    "citations": [["employee_travel_policy.pdf", 3]],
    "refusal_reason": null
  },
  {
    "query_id": "Q03",
    "role": "employee",
    "question": "What discount ceiling applies to Project Aurora?",
    "access_decision": "denied",
    "answer": "Access denied. The information you requested is contained in a document ...",
    "citations": [],
    "refusal_reason": "The requested information exists in a management-confidential document ..."
  }
]
```

---

## Adjusting the PoC

| What to change | Where |
|---|---|
| Model or temperature | `config.yaml` |
| Azure credentials / embedding deployment | `.env` |
| Evaluation assertions | `evals/run_basic_eval.py` |

---

## Running the basic evaluation

```bash
python evals/run_basic_eval.py
```

Place ground-truth files in `evals/ground_truth/`.  See `evals/run_basic_eval.py`
for the expected format.

---

## Unconfirmed assumptions (resolve before production)

| ID | Assumption |
|---|---|
| assumption_001 | Embedding deployment name from env var `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` |
| assumption_002 | RBAC implemented as Chroma `document_name` filter; pre-retrieval role detection via full-collection query |
| assumption_005 | Documents assumed to contain no personal data |
