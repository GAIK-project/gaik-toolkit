# Manufacturing Knowledge Base RAG Assistant — Proof of Concept

Role-aware, citation-grounded question answering over internal PDF documents.
Pre-retrieval RBAC is enforced from `access_manifest.json` so restricted content
never enters the language-model context.

---

## What this PoC does

1. **Loads** `poc_input_bundle.json` and resolves all sibling files from it.
2. **Indexes** the PDF documents page-by-page into a local in-memory vector
   index (Azure OpenAI embeddings, numpy cosine similarity). Each chunk carries
   `file_name`, `page_number`, `classification`, and `allowed_roles` metadata.
3. **Processes** every query in `query_set.json`:
   - Embeds the query and finds the top-1 match across **all** chunks.
   - If the top-1 match is in a document the requestor's role cannot access →
     `access_decision: denied`; the model never sees restricted text.
   - Otherwise → retrieves the top-4 permitted chunks and calls **gpt-5.4**
     (Azure OpenAI, temperature 0.0, reasoning effort medium) to generate a
     grounded, cited answer.
4. **Saves** `output/results.json` — a list of `RAGAnswerRecord` objects.

---

## Prerequisites

- Python 3.11+
- Dependencies: `pip install -r requirements.txt`
- Azure OpenAI resource with a chat deployment (gpt-5.4) and an embedding
  deployment accessible via API key.

---

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure credentials
cp .env.example .env
# Open .env and fill in AZURE_API_KEY, AZURE_ENDPOINT, AZURE_API_VERSION,
# AZURE_CHAT_DEPLOYMENT, and AZURE_EMBEDDING_DEPLOYMENT
```

---

## Running the PoC

```bash
python run_poc.py --input C:\Users\h02317\Downloads\runs\run_01\wizard_input\poc_input_bundle.json
```

Replace the path with the actual location of `poc_input_bundle.json`.
The files `access_manifest.json`, `query_set.json`, and the three PDFs are
resolved automatically relative to the bundle file.

Results are written to `output/results.json`.

---

## Expected PoC behaviour

| Query | Role | Expected decision | Key facts to verify |
|---|---|---|---|
| Q01 | employee | allowed | EUR 180/night, Finance Director approval required above limit, cite `[employee_travel_policy.pdf, 3]` |
| Q02 | employee | allowed | Inspect every 250 operating hours, replace after 1,000 h or 1.8 bar, cite manual pages 3 and 4 |
| Q03 | employee | **denied** | Project Aurora is management-confidential; `citations: []`, no restricted facts in answer |
| Q04 | manager | allowed | 12% discount ceiling, written CFO approval required above it, cite `[project_aurora_pricing_strategy.pdf, 3]` |

---

## Output schema — RAGAnswerRecord

```json
{
  "query_id": "Q01",
  "role": "employee",
  "question": "...",
  "access_decision": "allowed",
  "answer": "...",
  "citations": [["employee_travel_policy.pdf", 3]],
  "refusal_reason": null
}
```

`refusal_reason` is a non-null string only when `access_decision` is `"denied"`.
`citations` is always an empty list on denied records.

---

## Configuration

| What to change | File |
|---|---|
| Model name, temperature, reasoning effort | `config.yaml` → `models:` |
| RAG top-k, chunk size, overlap | `config.yaml` → `rag:` |
| Azure credentials and deployment names | `.env` |
| Evaluation metrics | `evals/run_basic_eval.py` |

---

## Running the basic evaluation

```bash
python evals/run_basic_eval.py
```

Requires ground-truth files in `evals/ground_truth/`.

---

## Next steps

- Run the PoC and paste `output/results.json` into the wizard chat.
- The wizard will help you interpret results and refine (Gate 3).
