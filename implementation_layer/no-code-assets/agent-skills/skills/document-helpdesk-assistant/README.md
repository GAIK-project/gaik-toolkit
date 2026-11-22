# Document helpdesk assistant (agent skill)

An agent skill that turns a folder of your own documents (price lists, catalogues, guides, terms, FAQs) into a helpdesk assistant. It reads the documents into a searchable knowledge folder, then answers questions **only from them**, names the document and section for every fact, recommends the best-fitting items from a catalogue, and writes a hand-off message when a person is needed.

> **This is a proof of concept.** It tests the idea on your own material inside an agent session: no website, no login, no ticketing, no memory between sessions, and it cannot send anything. For a complete application, use the **GAIK Solution Wizard** (`implementation_layer/solution_wizard/`) or build on GAIK's components in the [GAIK toolkit](https://github.com/GAIK-project/gaik-toolkit).

The same behaviour is available as a plain prompt for chat apps: **Document helpdesk assistant** in `no-code-assets/prompts/`. Use the prompt when you only attach files to a chat. Use this skill when your agent can run Python and read a folder, which gives it a real search over the documents instead of reading everything in one go.

## What it does

- Reads `.txt .md .csv .tsv .xlsx .docx .pdf` into chunks: a table row is one chunk written as `column: value | column: value`, text is split at headings and paragraphs.
- Searches them (`scripts/knowledge.py search`), lists complete catalogue rows with filters (`rows`) and shows the passages around a hit (`read`).
- Answers in your language with sources, exact prices and dates, and a clear "not in the documents" when it is not.
- Treats the documents as data: instructions written inside a document are not followed.
- Keeps a list of the questions it could not answer, which shows what is missing from your documents.

## Install and use

- **Claude Code, Codex, Copilot, VS Code:** install the GAIK agent plugin (see the [plugin README](../../README.md)), then ask: *"Use the document-helpdesk-assistant skill on the documents in my `<folder>`."*
- **claude.ai with code execution, other agents:** upload the skill `.zip` from the demo website's Skills page, or point the agent at this folder, and give it the documents.
- The agent asks for the organisation, what it does, the topics and the contact for a person, runs `prepare`, and starts answering.

Needs Python 3.10 or later (standard library only). PDFs need `pdftotext` (poppler), `pypdf` or PyMuPDF; a scan without a text layer has no text and is reported.

## The script on its own

```bash
python scripts/knowledge.py prepare ./documents --out ./helpdesk-knowledge
python scripts/knowledge.py overview ./helpdesk-knowledge
python scripts/knowledge.py search ./helpdesk-knowledge "extra monitor price" --top 5
python scripts/knowledge.py rows ./helpdesk-knowledge --source catalogue --where suitable_for=managers
python scripts/knowledge.py read ./helpdesk-knowledge D2#17 --around 1
```

Nothing leaves your machine; the script makes no network calls.

## Good documents

Clear table headings (`price_eur`, `availability`, `suitable_for`), one row per item, contact details and hand-off rules written in the documents ("group bookings go to sales"), and text PDFs rather than scans. Do not use confidential or personal material in a session you have not approved for it.

## Limits

It is as good as the documents, and the model can still make mistakes with long texts or large tables; check the cited source for anything that matters. The search is a word search with light stemming, not a semantic one, so the agent searches again with synonyms when needed. For meaning-based search over many documents, build on GAIK's RAG components.

## Tests

`implementation_layer/unit_tests/test_document_helpdesk_skill.py` tests the script on generated Excel, Word, CSV and text files (reading, chunking, search, filters, injection text, broken files) and checks the skill's rules.
