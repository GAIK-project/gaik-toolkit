---
name: component-check
description: Runs gaik's schema generator (flat, nested-list and two-list schemas, every field type, date formats and defaults), extractor, vision extractor, RAG pipeline (embedder, in-memory vector store, retriever, answer generator with citations), tabular agent and vision parser on synthetic invoices (Finnish and English text, a PDF, a scanned PNG and a CSV) with one or more providers (Azure, OpenAI, Google, Vertex, CSC Aitta, Anthropic, Anthropic on Foundry), checks each output against expected fields, types, values, numbers, citations and text, can have a subscription CLI (Claude Code, Codex or Antigravity) judge every output without an API key, and compares a run with an earlier one. Also gives the browser steps for the same checks on the deployed demo's schema-generator, extractor and vision-extractor pages. Use before tagging a gaik release, after a change to the extractor, schema generator, vision extractor, RAG components, tabular agent, vision parser or LLM layer, to compare providers or models, or for "testaa komponentit", "aja komponenttitestit", "toimiiko extractor eri malleilla", "check the components before a release". Manual and local; the same runner also runs in the live-smoke workflow. The release certification gate is scripts/release_check.py, not this skill.
---

# Component check

`run_checks.py` runs the cases in `cases.json` once per provider, with the gaik that Python
imports (in this repository, the editable checkout). Schema cases run first; an extraction case
reuses the schema its `schema_from` case generated for the same provider, so a provider is tested
end to end, the way the demo's pages chain them. The RAG, tabular agent and vision parser cases
stand alone. Every input is synthetic (`fixtures/`, made by `make_fixtures.py`). Each output is
checked by fixed rules, and optionally by a judge.

## The cases

| Case | Component | What it checks |
| --- | --- | --- |
| `schema-invoice-types` | schema generator | Flat schema from a Finnish task: date, decimal, a three-value enum, no extra field |
| `schema-invoice-lines` | schema generator | Header fields with one nested list, `line_items` |
| `schema-inventory-list` | schema generator | `nested_list`: only a list, named `inventory_items`, of records with an int, a decimal and an enum |
| `schema-meeting-two-lists` | schema generator | Header fields with two separate lists, `participants` and `action_items` (with a date) |
| `schema-field-rules` | schema generator | Flat: a bool, an int, a date with format `DD.MM.YYYY` (`%d.%m.%Y`), a `list[str]` and a stated default `"not given"` |
| `extract-invoice-text` | extractor | Finnish invoice text: total with VAT, Finnish date and decimal comma |
| `extract-two-documents` | extractor | A Finnish and an English invoice give two records in order |
| `extract-invoice-lines` | extractor | The three line items into the nested schema |
| `vision-invoice-pdf`, `-png` | vision extractor | The same values from the PDF and from a scan without a text layer |
| `vision-invoice-lines` | vision extractor | The line items read from the PDF |
| `rag-invoice-total` | RAG | Both invoices indexed in memory; the answer to "total including VAT of INV-2026-0042" holds 551,57 and a citation resolves to `invoice-fi.txt` |
| `tabular-invoice-lines` | tabular agent | The sum of one invoice's `line_total` in `invoice-lines.csv`: 439.50 in the query rows and in the answer |
| `parse-invoice-pdf` | vision parser | The PDF as markdown keeps INV-2026-0042, Esimerkki Oy, Tiivistesarja and 551,57 (a typographic dash counts as a hyphen; gpt-6-luna writes en dashes in the invoice number) |

The RAG case builds its chunks itself (one per invoice, which is one page) and uses no parser.
gaik's answer generator returns its answer as text, so the runner reads the citations in the
form gaik asks for, `[document_name, page X]`, and resolves each against the metadata of the
chunks the retriever returned: a citation that names no retrieved chunk is a failure.

## Run it

1. `uv sync --all-extras` once. The run prints which gaik it imports; it should be this
   checkout's `implementation_layer/src/gaik`.
2. Choose the providers and give their keys. Keys come from the environment or from
   `--env-file` (repeatable; values are never printed or written). A provider without its keys
   is reported as not configured and its cases as `skip`; `--require-all` turns that into a
   failure.
3. Start the run, in the background if more than one provider (a provider takes one to three
   minutes; providers run in parallel):

   ```bash
   uv run python .claude/skills/component-check/run_checks.py \
       --providers azure,aitta --env-file <path to .env> --out <folder outside the repository>
   ```

   - `--list` shows the cases; `--only <ids>` or `--component vision_extractor` runs some (a
     chosen extraction case brings its schema case).
   - `--model azure=<deployment>` picks a model (repeatable). Otherwise `CHECK_<PROVIDER>_MODEL`,
     then `RELEASE_<PROVIDER>_MODEL`, then gaik's own default for the provider. A separate vision
     model (vision extractor and vision parser): `CHECK_<PROVIDER>_VISION_MODEL`. The RAG
     case's embedding model: `CHECK_<PROVIDER>_EMBEDDING_MODEL`, then
     `RELEASE_<PROVIDER>_EMBEDDING_MODEL`, then gaik's default (`EMBEDDING_MODEL`, else
     `text-embedding-3-small` on Azure and OpenAI, `gemini-embedding-001` on Google and Vertex;
     Azure has the deployments `text-embedding-3-small` and `text-embedding-3-large`). The
     summary names the models each provider used. Check the provider's current model catalogue
     before naming one; do not copy an old example.
   - `--baseline <earlier run folder>` adds a section on cases that passed then and do not now,
     outputs that changed, and generated schemas whose names, types, enums or structure changed
     (descriptions are ignored: their wording varies from run to run).
   - `--reuse-schemas <earlier run folder>` takes that run's schemas instead of generating new
     ones, to test the extractors on a fixed schema (and to save calls). It cannot rebuild a
     schema the generator classed as `nested_list`; run such a case without it.
   - `--provider-timeout <s>` (default 900) stops waiting for a provider that has run that long
     since it started; its unfinished cases are errors and the summary is still written.
   - `--public` keeps only error types and status codes, no provider error text: for a run
     whose results are published, such as the live-smoke workflow.
   - `--attempts 2` runs a case that failed or errored once more, as the demo's `api/smoke.py`
     does. The summary marks the cell `(attempt 2)` and lists the first attempt's problems
     under "Needed another attempt", so a flaky case stays visible (open issue #94: the
     schema generator now and then keeps only the first field). The live-smoke workflow and
     the release job use 2; a case that fails twice still fails the run.
   - `--judge claude|codex|agy` (below).
4. Read `<out>/summary.md` and report from it.

| Provider | Keys it needs (gaik's names) |
| --- | --- |
| `azure` | `AZURE_API_KEY`, `AZURE_ENDPOINT` (model: `AZURE_DEPLOYMENT`) |
| `openai` | `OPENAI_API_KEY` |
| `google` | `GOOGLE_API_KEY` or `GEMINI_API_KEY` |
| `vertex` | `GOOGLE_PROJECT_ID` or `GOOGLE_CLOUD_PROJECT`, with service-account credentials |
| `aitta` | `AITTA_API_KEY` (model: `AITTA_MODEL`); CSC's terms forbid personal data |
| `anthropic` | `ANTHROPIC_API_KEY` |
| `anthropic_foundry` | `ANTHROPIC_FOUNDRY_API_KEY` (or `AZURE_API_KEY`), `ANTHROPIC_FOUNDRY_RESOURCE` |

Anthropic and Anthropic on Foundry have no embeddings API, so their RAG case is a `skip` with
that reason; Aitta's needs `CHECK_AITTA_EMBEDDING_MODEL` (or `AITTA_EMBEDDING_MODEL`), since
gaik has no default embedding model there. The summary lists every such skip and its reason.

The component calls go to the providers' APIs and use these keys: gaik has no subscription
path. Azure is the Haaga-Helia default and costs the project nothing. A full run is about
thirty requests per provider. The vision parser case also imports gaik's parsers package,
which loads Docling: that takes half a minute or more the first time.

## The judge runs on a subscription

The fixed checks catch a wrong value, type or count. `--judge` also gives every output, with
its input and the case's `rubric`, to a local CLI and records its verdict and the defects it
names:

| `--judge` | CLI | Signed in with |
| --- | --- | --- |
| `claude` | `claude -p` (no tools, no MCP servers) | `claude` then `/login` with the Claude subscription |
| `codex` | `codex exec --sandbox read-only`, model `gpt-6.2-sol` | `codex login` with ChatGPT |
| `agy` | Antigravity `agy -p --mode plan --sandbox` | the Antigravity Google sign-in |

The runner removes every API key, token and alternative endpoint from the judge's environment
(`judge_env` in `run_checks.py`), so the CLI falls back to its own login. Before any component
call it also asks the CLI how it is signed in (`claude auth status` must say `claude.ai`,
`codex login status` must say ChatGPT) and stops when that is not a subscription, for example
a Claude Code `apiKeyHelper` or a Codex API-key login. Antigravity has no status command and
signs in with Google only. A judge that hits its plan's usage limit gives `judge error` with
the CLI's message; the fixed checks still stand.

`--judge-model` (or `CHECK_JUDGE_MODEL`) picks the CLI's model. Codex gets `gpt-6.2-sol` unless
you name another; Claude Code and Antigravity use their own default. Give a judge only
synthetic or otherwise shareable inputs: it sends them to its own provider under the
subscription's terms.

The judge is advice. A `judge fail` on a case the fixed checks pass is a finding only after
you have read the output and agree; say which.

## Read the result

A cell marked `(warning)` passed with a note under "Warnings": the vision parser's markdown
held a value only once its typographic dashes were read as hyphens (`INV–2026–0042` for
`INV-2026-0042`). That is a fidelity defect of the model's copy, reported, not failed.

`summary.md` has one row per case and a column per provider (`pass`, `fail`, `error`, `skip`,
and the judge's verdict), then every failure with its problems and every skip with its reason.
Beside it, per provider and case: `checks.json` (problems, usage, the judge's answer),
`result.json` (an extractor's output; the RAG answer with the retrieved chunks and resolved
citations; the tabular agent's answer, SQL and rows; the parser's markdown) or
`requirements.json`, `json_schema.json` and `structure.json` (a generated schema; the last
names a nested list's container). Embedder, answer generator and tabular agent report no token
usage themselves, so the runner counts the usage of the calls made through their own client.

- `fail` means the output broke a fixed check: quote the problems from the summary and the
  value from `result.json`. A schema case checks both the parsed requirements and the
  generated model's JSON schema (`model: ...` problems). A schema case that fails skips the cases built on it; rerun with
  `--keep-going` to see them anyway.
- `error` is an exception: its type and message (credentials redacted; no message with
  `--public`) are in `checks.json`.
  A timeout, 429 or 5xx comes from the provider, not gaik: run that provider again with
  `--providers <one> --only <case>` before calling it a regression.
- One provider failing a case the others pass points at the provider or model; every
  provider failing it points at gaik. Compare with a baseline run from the last release to tell
  a regression from an old weakness.
- A component change found this way goes to the user as a proposed change: this repository
  changes gaik's components only with their approval (AGENTS.md).

## The deployed demo

The same checks by hand on `https://gaik-demo.2.rahtiapp.fi` (or a local `bun run dev`), in a
browser where the user has signed in with an approved account. Use only the files in
`fixtures/`, and mind the demo's per-user rate limits and trial allowance.

1. **`/schema-generator`**: paste the `requirements` of `schema-invoice-types` from
   `cases.json`. The field table should list the five fields with the types the case expects
   (date, decimal number, currency limited to EUR, USD and SEK). The download is a zip with
   `schema.py` and `requirements.json`. Repeat with `schema-invoice-lines`: the line items are a
   nested list.
2. **`/extractor`**: give the same requirements and paste `fixtures/invoice-fi.txt`, then also
   `invoice-en.txt` as a second document. Compare the values with `extract-two-documents` in
   `cases.json`. With sources on, every value should have a checked quote.
3. **`/vision-extractor`**: upload `invoice-fi.pdf`, then `invoice-fi.png`, with the same
   requirements, and compare with the vision cases. Try a model of each provider the menu offers.

Report what each page showed beside what the case expects. The deployed demo runs the gaik
release on PyPI, not this checkout, so a fix here reaches it only after a release.

## Before a release

1. Offline tests and the wizard checks (AGENTS.md).
2. This check with the providers the release changes, `--baseline` on a run from the last
   release, and a judge if there are failures to explain.
3. In GitHub: `gh workflow run live-smoke.yml -f providers=azure` (Actions, "Live smoke") runs
   `scripts/release_smoke.py` and this runner on the chosen branch without a tag. Only the
   providers with keys in the repository's secrets can run there.
4. The certification itself: `scripts/release_check.py --live --version X.Y.Z` (AGENTS.md).
   On the tag, the release job runs it and then this runner on Azure (`--public`); a failed
   case blocks the PyPI publish, so a case that fails at step 2 or 3 must be fixed first.

## Add or change a case

Edit `cases.json`: an `id`, a `component` (`schema_generator`, `extractor`, `vision_extractor`,
`rag`, `tabular_agent` or `vision_parser`), a `title`, a `rubric` for the judge, and an `expect`
block.

- A schema case has `requirements`, written as a user would and naming every field and list;
  `expect` names its `fields` with the allowed types, `exact_fields`, `enums`, `formats` (a
  date's strftime format), `defaults` (a stated default, also in the model) and
  `structure_type`. A `nested_list` names its list in `container`. A schema with child lists
  has `children` (list name to fields, exact with `exact_fields`) or, for one list,
  `child_container` and `child_fields`.
- An extraction case has `schema_from` and `documents` (extractor) or `files` and `source_text`
  (vision), and `expect.records`, or `expect.parent` with `items_key` and `items` for a nested
  schema.
- A `rag` case has `documents`, a `question` and optionally `top_k` (default 5, the
  retriever's own); `expect.answer_contains` lists strings, or
  lists of alternatives, the answer must hold, and `expect.cited_document` the document a
  citation must resolve to.
- A `tabular_agent` case has `files` and a `question` with one numeric answer,
  `expect.number`, which must be in the query's rows and in the answer.
- A `vision_parser` case has `files` and `source_text`; `expect.contains` lists what the
  markdown must hold, like `answer_contains`.

Values and texts are compared after normalising case, spaces, number formats (`1 234,50`,
`1,250.00`) and dates; in `answer_contains` and `contains` a typographic dash also reads as a
hyphen. Inputs stay synthetic; a new PDF or image comes from `make_fixtures.py`.
`--cases <file>` runs another case file of the same form, for example one the user keeps
outside the repository.

`implementation_layer/unit_tests/test_component_check_skill.py` checks the runner's logic and
that every case is consistent with its fixtures, offline; it runs in CI.
