---
name: component-check
description: Runs gaik's schema generator, extractor and vision extractor on synthetic invoices (Finnish and English text, a PDF and a scanned PNG) with one or more providers (Azure, OpenAI, Google, Vertex, CSC Aitta, Anthropic, Anthropic on Foundry), checks each output against expected fields, types and values, can have a subscription CLI (Claude Code, Codex or Antigravity) judge every output without an API key, and compares a run with an earlier one. Also gives the browser steps for the same checks on the deployed demo's schema-generator, extractor and vision-extractor pages. Use before tagging a gaik release, after a change to the extractor, schema generator, vision extractor or LLM layer, to compare providers or models, or for "testaa komponentit", "aja komponenttitestit", "toimiiko extractor eri malleilla", "check the components before a release". Manual and local; the same runner also runs in the live-smoke workflow. The release certification gate is scripts/release_check.py, not this skill.
---

# Component check

`run_checks.py` runs the cases in `cases.json` once per provider, with the gaik that Python
imports (in this repository, the editable checkout). Schema cases run first; an extraction case
reuses the schema its `schema_from` case generated for the same provider, so a provider is tested
end to end, the way the demo's pages chain them. Every input is synthetic (`fixtures/`, made by
`make_fixtures.py`). Each output is checked by fixed rules, and optionally by a judge.

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
     model: `CHECK_<PROVIDER>_VISION_MODEL`. The summary names the model each provider used.
     Check the provider's current model catalogue before naming one; do not copy an old example.
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

The component calls go to the providers' APIs and use these keys: gaik has no subscription
path. Azure is the Haaga-Helia default and costs the project nothing. A full run is about a
dozen requests per provider.

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

`summary.md` has one row per case and a column per provider (`pass`, `fail`, `error`, `skip`,
and the judge's verdict), then every failure with its problems. Beside it, per provider and
case: `checks.json` (problems, usage, the judge's answer), `result.json` (an extractor's output)
or `requirements.json` and `json_schema.json` (a generated schema).

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

## Add or change a case

Edit `cases.json`: an `id`, a `component` (`schema_generator`, `extractor` or
`vision_extractor`), a `title`, a `rubric` for the judge, and an `expect` block. A schema case has
`requirements`; `expect` names its `fields` with the allowed types, `exact_fields`, `enums`,
`structure_type` and for a nested schema `child_container` and `child_fields`. An extraction case
has `schema_from` and `documents` (extractor) or `files` and `source_text` (vision), and
`expect.records`, or `expect.parent` with `items_key` and `items` for a nested schema. Values are
compared after normalising case, spaces, number formats (`1 234,50`, `1,250.00`) and dates.
Inputs stay synthetic; a new PDF or image comes from `make_fixtures.py`. `--cases <file>` runs
another case file of the same form, for example one the user keeps outside the repository.

`implementation_layer/unit_tests/test_component_check_skill.py` checks the runner's logic and
that every case is consistent with its fixtures, offline; it runs in CI.
