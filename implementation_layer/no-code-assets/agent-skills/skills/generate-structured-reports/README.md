# generate-structured-reports

An [Agent Skill](https://agentskills.io/specification) that writes a **source-cited report**
from your files with the [`gaik`](https://pypi.org/project/gaik/) report writer. Every statement
in the report traces to a quote from one of your sources, the quotes are checked against those
sources, and the report says plainly what the sources do not cover and where they disagree.

The skill runs gaik's three-stage pipeline instead of having the agent write the report from
memory:

1. **Normalize**: every file (PDF, Word, spreadsheet, text, recording, image) becomes text that
   keeps its file name.
2. **Curate**: for each section, facts paired with the exact words they came from, the required
   items no source covers, and the conflicts between sources.
3. **Synthesize**: each section is written from its own facts only, then checked by a reviewer
   model; a summary is written from the sections it depends on.

It runs through a Python helper in `scripts/`, so it needs an agent that can execute code and
a machine where `gaik` is installed. See [Where it runs](#where-it-runs). Where the agent cannot
run code, use the [`report-writing`](../report-writing) skill instead.

## Use it when

- a report must be written from source material and every statement must trace to a source;
- you have a fixed report template, such as a condition assessment, inspection report or
  project report, and want it filled from evidence;
- your material is mixed: site notes, recordings, photos, earlier reports, spreadsheets;
- you want the gaps and contradictions in the material visible in the report, not smoothed
  over.

Example requests:

```text
Use the generate-structured-reports skill to write a condition assessment from the files in
inputs/, following the template in condition_template.docx.
```

```text
Write a project status report from these meeting recordings and the risk register. 
```

## What you get

The agent saves everything in one run folder, in a location you choose (by default under your
home folder), and leaves your original files where they are.

**The report**

- **Report (Markdown and MS WORD):** the finished report, with your sections in order.
- **Review log:** what the reviewer changed in each section, and the edits that could not be applied.

In the report, each fact is cited by its source file and place (page, sheet and row, or heading)
if you want citations; the agent asks at the start, and without them the report does not show
where each fact came from. Markers such as "(missing: item)" show where a required item has no
source, and unresolved conflicts between sources are stated in the text.

**The evidence behind it**

- **Normalized sources:** every source converted to Markdown text with its file name kept, and an
  index of the sources with their converter and class (primary or secondary).
- **Curated knowledge:** for each section, the fact units (a summary and the exact quote it came
  from, checked against its source), the required items no source covers, and the conflicts. You
  can correct facts here and write the report again.

**What each stage recorded**

- **Normalization diagnostics:** each source's converter and text length, and the token usage of
  transcription and image description.
- **Curation diagnostics:** per section, the fact count, missing items and conflicts; the facts
  dropped because their quote could not be verified, and why; token usage.
- **Synthesis diagnostics:** token usage, the number of missing-item markers, the reviewer edits
  applied and unresolved, and whether the Word export succeeded.
- **Run record:** what each stage was built from, so the agent can tell a current report from one
  built on inputs or settings that have since changed.

**The spec and the structure**

- **Report spec:** the agreed specification: title, language, sections with their instructions
  and required items, report-wide instructions, sources, models and settings. It holds no keys.
  Keep it to rerun or adjust the report.
- **Spec proposal:** the whole-spec proposal you reviewed in chat, with your changes.
- **Corrections log:** a note of each correction you approved in a normalized text, such as a
  misheard name, with the source that supports it.

**A reusable template**

- **Saved template:** the structure of an accepted report (title, language, report-wide
  instructions and sections), saved in your template library, outside the run folder, only if you
  agree, and never with sources, facts or keys. See [Template library](#template-library).

## Template library

When you give no template, the agent searches your template library for one that fits your
request, shows what it found, and asks whether to use it. A library template is only a draft:
you review its sections in the chat like any other structure. When you finish a structure that
is new, the agent offers to save it, shows exactly what would be saved, and writes it **only if
you agree**.

- **What is saved:** the report's title and language, the report-wide instructions, and the
  sections with their prompts and required items. Never your sources, facts, file paths, models
  or keys.
- **Where:** one JSON file per template in `report-templates` under your home folder, or in the
  folder named by the `GAIK_REPORT_TEMPLATES` environment variable. It is outside the skill, so
  a skill update does not replace it, and outside any git repository: the helper refuses to
  save into a git working tree or into the skill's folder.
- **Search:** by the words of your request, matched against each template's name, keywords,
  description and section titles. It makes no model call. Give a template a few keywords you
  would search with.
- **Shared libraries:** point `GAIK_REPORT_TEMPLATES` at a shared folder to share templates.
  Saving never overwrites an existing template unless you agree to update it.
- **Needs file access:** the agent must be able to read and write that folder, as in Claude
  Code and Codex. A chat without file access cannot use the library.

You can also use the helper yourself: `python scripts/template_library.py list`.

## Where it runs

The skill is a set of instructions plus a Python helper. The agent follows the instructions and
the helper does the work, so the agent must be able to **run Python on a machine that has `gaik`
installed and your provider's API key in its environment**, with network access to the provider.

**Recommended: run it in Claude Desktop's Claude Code section.** Before running the skill, set
the API keys on your computer as environment variables (for example in PowerShell with the
`setx` command, see [Setting the keys as environment variables](#setting-the-keys-as-environment-variables)).
Claude Desktop's Claude Code section then reads those keys from the environment, and you never
type a key into the chat.

| Where you run it | Keys | Status |
|---|---|---|
| **Claude Code**: Claude Desktop's Claude Code section, the Claude Code CLI, or VS Code with the Claude Code plugin | Read from environment variables saved on your computer (safer) | Recommended. Tested end to end in the CLI |
| **Codex**: the ChatGPT app, or the Codex plugin in VS Code | Read from environment variables saved on your computer (safer) | Runs end to end. Tested in the CLI |
| **Claude Desktop chat, claude.ai chat, claude.ai's Claude Code** | Cannot read environment variables: the keys must be typed directly into the chat | Can run the skill, but unsafe and not recommended. Not tested |

Where the agent cannot run code at all, use the [`report-writing`](../report-writing) skill
instead. It has Claude write the report itself, without the quote checks.

## Installing the skill
For **Running in Claude Desktop --> Claude Code**:

1. Get a `.zip` of the skill: download `generate-structured-reports.zip` from the
   [demo app's skills page](https://gaik-demo.2.rahtiapp.fi/skills), or zip the
   `generate-structured-reports` folder yourself with `SKILL.md` directly inside it.
2. Open **Customize → Skills → Add → Upload skill** and choose the `.zip`.

For running with **Claude Code in VS Code or CLI**, save the skill folder in ~/.claude/skills at user or project level. 

For running with **Codex (ChatGPT Codex, CLI, or Codex plugin in VS Code)**, save the skill folder in ~/.agents/skills at user or project level. 

Then, the skill can be invoked as follows:

```text
Use the generate-structured-reports skill to write a project status report from these meeting recordings and the risk register. 
```

When the skill starts for the first time, it installs all the dependencies it needs. You
only need Python 3.11 or later and an API key (see [Providers and API keys](#providers-and-api-keys)).

**Required, installed when a run needs them:**

- `gaik[report-writer]`, the Python package that does the work.
- For Anthropic, Google or LiteLLM as the provider: that provider's gaik extra (`llm-anthropic`,
  `llm-google` or `llm-litellm`). The helper installs it itself.
- For recordings and video: ffmpeg, which reads and converts them, and, on Python 3.13 or later,
  `audioop-lts`, which Python 3.13 removed from the standard library. Without them, normalizing a
  recording fails.
- For Word output: Pandoc, downloaded into your user folder with no administrator rights, and
  only if you agree. If you say no, the report is Markdown only.

**Optional, only if you need them:**

- Docling (`gaik[parser]`), gaik's advanced PDF parser, for richer table and layout extraction
  from complex PDFs.
- PyTorch, for GPU-accelerated parsing in image- and OCR-heavy flows.


## Providers and API keys

The workflow works with any provider gaik supports. For instance, if you have an openAI key, all you need to do before starting the skill workflow is to set the API key as local environment variable as follows:

```powershell
setx OPENAI_API_KEY "openai_api_key"
```

You can then start the skill.

While the skill can work with gaik supported providers, if the sources include recordings that need transcription, gaik transcriber requires an Azure OpenAI or OpenAI key. The whole run uses a single provider, so for such a run that provider is Azure OpenAI or OpenAI for every stage.

The default provider is `openai`. To use another, set `LLM_PROVIDER` or tell the agent which
provider to use, and set that provider's variables below.

| Provider (`--provider`) | Variables |
|---|---|
| `openai` | `OPENAI_API_KEY`; optionally `OPENAI_MODEL`, `OPENAI_TRANSCRIPTION_MODEL` |
| `azure` (Azure OpenAI) | `AZURE_API_KEY`, `AZURE_ENDPOINT`; optionally `AZURE_DEPLOYMENT`, `AZURE_TRANSCRIPTION_MODEL` |
| `anthropic` | `ANTHROPIC_API_KEY`; optionally `ANTHROPIC_MODEL` |
| `anthropic_foundry` (Claude on Azure Foundry) | `ANTHROPIC_FOUNDRY_API_KEY` or `AZURE_API_KEY`, and `ANTHROPIC_FOUNDRY_RESOURCE`; optionally `ANTHROPIC_MODEL` |
| `google` | `GOOGLE_API_KEY` or `GEMINI_API_KEY`; optionally `GOOGLE_MODEL` |
| `vertex`, `openai_compatible`, `litellm`, `aitta` | See gaik's LLM configuration for their variables |

### Setting the keys as environment variables

Set the variables once and the skill reads them every time. In Windows PowerShell, `setx`
writes a variable permanently into the Windows registry, in your user environment, so it
survives restarts and is read by the skill without anything in the chat.

OpenAI:

```powershell
setx OPENAI_API_KEY "openai_api_key"
```

Azure OpenAI (`AZURE_API_VERSION` is optional; gaik has a default):

```powershell
setx AZURE_API_KEY "azure_api_key"
setx AZURE_ENDPOINT "azure_endpoint"
setx AZURE_API_VERSION "azure_api_version"
```

Anthropic:

```powershell
setx ANTHROPIC_API_KEY "anthropic_api_key"
```

Anthropic on Azure Foundry:

```powershell
setx ANTHROPIC_FOUNDRY_API_KEY "anthropic_foundry_api_key"
setx ANTHROPIC_FOUNDRY_RESOURCE "anthropic_foundry_resource"
```

To use a provider other than the default `openai` for every run, also set
`setx LLM_PROVIDER "azure"` (or `anthropic`, `anthropic_foundry`, `google`). `setx` applies only to programs started afterwards, so close
and reopen the terminal, and restart Claude Desktop, Visual Studio Code or the ChatGPT
application. PowerShell keeps typed commands in its history, so clear the entry afterwards if
others can read it.

macOS and Linux, for the OpenAI key (the other providers work the same way with their own
variable names). Add the line to your shell profile, `~/.zshrc` on macOS or `~/.bashrc` on
Linux, then open a new terminal:

```bash
echo 'export OPENAI_API_KEY="openai_api_key"' >> ~/.zshrc
```

On macOS, applications opened from the Dock do not read the shell profile; start the client from
a terminal in which the variable is set.

### Changing the provider and the models

The default provider is `openai` (`LLM_PROVIDER`). The default models depend on the provider,
and are used when nothing else names a model:

| `LLM_PROVIDER` | Curator (`GAIK_REPORT_CURATOR_MODEL`) | Writer (`GAIK_REPORT_WRITER_MODEL`) | Reviewer (`GAIK_REPORT_REVIEWER_MODEL`) |
|---|---|---|---|
| `openai`, `azure` | `gpt-6-luna` | `gpt-6-luna` | `gpt-6.1-sol` |
| `anthropic`, `anthropic_foundry` | `claude-sonnet-5` | `claude-sonnet-5` | `claude-sonnet-5-5` |
| `google`, `vertex` | `gemini-3.6-flash` | `gemini-3.6-flash` | `gemini-3.8-flash` |
| `openai_compatible`, `aitta`, `litellm` | the provider's configured model | the same | the same |

**With environment variables** (for every report), in PowerShell:

```powershell
setx LLM_PROVIDER "azure"
setx GAIK_REPORT_WRITER_MODEL "writer_model_name"
setx GAIK_REPORT_REVIEWER_MODEL "reviewer_model_name"
```

**With the report's config JSON** (for one report), in the `models` section of
`report_spec.json`. It overrides the variables:

```json
"models": {
  "curator": "curator_model_name",
  "writer": "writer_model_name",
  "reviewer": "reviewer_model_name"
}
```

The config JSON has no provider field: the provider is always `LLM_PROVIDER`, or the provider
the agent is told to use for the run.

How a model is chosen, for each of the three steps:

1. the report spec's `models` entry, if it has one;
2. else the variable in the table, if it is set;
3. else the default for the provider in the table above;
4. else, for a provider without a default, the model configured for it.

So:

- A model name means something only to the provider the run uses, and a run uses a single
  provider for every step. The defaults follow the provider you choose, so changing
  `LLM_PROVIDER` also changes the default models.
- On Azure OpenAI and Anthropic on Azure Foundry the names are your **deployment names**, so a
  deployment must exist for each.
- `OPENAI_MODEL`, `AZURE_DEPLOYMENT`, `ANTHROPIC_MODEL` and `GOOGLE_MODEL` do not set these three
  steps; use the variables above.
- Changing a model marks the stage that used it as not current, and the agent reruns it.

**Reasoning effort** is not set by the skill: nothing is passed, so each model runs at its own
default. If your model supports it, set it per step in the report's config JSON:

```json
"settings": {
  "writer": {"reasoning_effort": "high"},
  "reviewer": {"reasoning_effort": "low"}
}
```

The curator has its own `curator` entry. Set it only for models that support it: the levels a
model accepts depend on the model, and a model that does not accept the setting rejects the
request, which stops the stage. gaik maps the setting for Anthropic models that take an effort
and drops it for Google models.
- `preflight` with `--check-provider` prints the provider and the model each step will use,
  and the run record keeps what each stage ran with.

### Alternative: a `.env` file

Put the variables of the provider you use in a `.env` file. This skeleton lists them by name;
fill in one provider's block, leave the others out, and never commit the file:

```dotenv
# Which provider the run uses: openai, azure, anthropic, anthropic_foundry or google.
# Leave it out to use openai.
LLM_PROVIDER=

# Optional model names for the three steps; the defaults are in the README.
GAIK_REPORT_CURATOR_MODEL=
GAIK_REPORT_WRITER_MODEL=
GAIK_REPORT_REVIEWER_MODEL=

# --- OpenAI ---------------------------------------------------------------
OPENAI_API_KEY=
# Optional
OPENAI_MODEL=
OPENAI_TRANSCRIPTION_MODEL=

# --- Azure OpenAI ---------------------------------------------------------
AZURE_API_KEY=
AZURE_ENDPOINT=
# Optional
AZURE_DEPLOYMENT=
AZURE_TRANSCRIPTION_MODEL=

# --- Anthropic ------------------------------------------------------------
ANTHROPIC_API_KEY=
# Optional
ANTHROPIC_MODEL=

# --- Anthropic on Azure Foundry -------------------------------------------
ANTHROPIC_FOUNDRY_API_KEY=       # or AZURE_API_KEY
ANTHROPIC_FOUNDRY_RESOURCE=
# Optional
# ANTHROPIC_MODEL=

# --- Google ---------------------------------------------------------------
GOOGLE_API_KEY=                  # or GEMINI_API_KEY
# Optional
GOOGLE_MODEL=
```

The helper reads environment variables, so load the file into the shell that starts the agent
(gaik may not find a `.env` on its own when it is installed with pip):

```bash
set -a; source .env; set +a       # macOS, Linux, Git Bash
```

```powershell
Get-Content .env | Where-Object { $_ -match '^\s*[^#\s][^=]*=' } | ForEach-Object {
  $name, $value = $_ -split '=', 2
  Set-Item "env:$($name.Trim())" ($value -replace '\s+#.*$', '').Trim()
}                                  # Windows PowerShell
```

The empty values are placeholders. Delete the blocks of providers you do not use and every
optional line you leave blank: some optional variables, such as the model names, would otherwise
be read as an empty value instead of the provider's default.

Limits that depend on the provider:

- **Recordings and video** are transcribed with the provider of the whole run, which must be
  `openai` or `azure`. With another provider, give a transcript instead.
- **Images** are described by the run's model, which must accept images.
- **Model names** (the variables or the spec's `models` section) must be names your provider
  knows; see [Changing the provider and the models](#changing-the-provider-and-the-models).
- The helper checks the provider before spending anything: `preflight` with `--check-provider`
  loads the configuration without a model call.

## Files

| File | Content |
|---|---|
| `SKILL.md` | The workflow the agent follows |
| `references/report-spec.md` | The spec's keys, source classes and priority, the files the pipeline reads |
| `references/report-structure.md` | Agreeing the structure in chat, the structure file, how a template is read, a worked example |
| `references/review-and-resume.md` | The workspace, diagnostics, corrections, Word export, what to rerun after a change |
| `scripts/run_report.py` | The stage helper: `preflight`, `propose-spec`, `apply-spec`, `normalize`, `set-sections`, `curate`, `validate-knowledge`, `synthesize`, `rebuild`, `update-sample` |
| `scripts/template_to_spec.py` | Drafts the structure from a Word or Markdown template |
| `scripts/template_library.py` | Searches, loads and saves your template library: `list`, `search`, `show`, `load`, `save` |
