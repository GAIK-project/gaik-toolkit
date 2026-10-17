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
Write a project status report from these meeting recordings and the risk register. There is no
template; propose the sections.
```

## What you get

- `report.md` and, with Pandoc installed, `report.docx`, with your template's sections in order.
- Each fact cited by its source file and place (page, sheet and row, or heading), if you want
  citations: the agent asks at the start. Without them the report does not show where each fact
  came from.
- `(missing: …)` markers where a required item has no source, and unresolved conflicts stated
  in the text.
- A short summary from the agent: missing items, unresolved conflicts, facts dropped because their
  quote could not be verified, reviewer edits that could not be applied, and pages that could
  not be read.
- A reusable `report_spec.json`, and a workspace with every stage's files, which you can
  correct and rerun from.

## The report structure

After your sources are converted to text, the agent shows you the whole report spec: the
report-wide fields and instructions, the sources and sample, the models and settings, and the
sections, each with its title, what it must contain, the facts it must cover, and which other
sections it is written from. Every value is a proposal you accept or change in the chat, one
group at a time, before anything is curated:

| You give | The agent proposes |
|---|---|
| A Word or Markdown template | One section per heading, with prompts drawn from the template's guidance text and checklists; it asks about anything unclear |
| A report spec JSON | Its sections |
| Nothing | A structure that fits your request and what the sources contain |
| An earlier filled report | It asks whether it is the template, a style sample, or both; its facts are never used unless you say it is evidence |

You can rename any section, rewrite any prompt, add, delete or reorder sections, make a section
a summary of others, or set the proposal aside and give your own structure. The agent points
out where a change would weaken the report, for example a prompt too vague to act on, and
explains the few rules: at least one section, at least one written from the sources rather
than only summaries, and different titles. Sections have one level: sub-sections become part
of a section's prompt.

The Word output follows the report's headings, not a branded template's page layout, logos or
fields.

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

## Checkpoints

The agent asks before spending money, then stops at the points where you decide:

- **The run settings**: before normalization, the sources, sample, models and settings.
- **The whole spec**: after normalization, every field, including the sections with their
  prompts, required items and dependencies, agreed in the chat.
- **The evidence**: after curation, what is missing, what conflicts and what was dropped. You
  can proceed with these marked, or correct the facts or add a source first.
- **Changes after delivery**: a wording change rebuilds the report with no model call; a fact
  change rewrites it; a new style sample needs no new processing of the sources.

## Where it runs

The skill is a set of instructions plus a Python helper. The agent follows the instructions, and
the helper does the work, so the agent must be able to **run Python on a machine that has `gaik`
installed and your provider's API key in its environment**. The helper calls the model provider
directly, so that machine also needs network access to it.

| Where you use it | Runs the skill? | Notes |
|---|---|---|
| **Claude Code** (CLI, Claude Desktop, VS Code plugin) | Yes (tested end to end in the CLI) | Runs on your machine and reads environment variables. Install the plugin, install `gaik`, set the key as an environment variable |
| **Codex** (ChatGPT app, VS Code plugin) | Yes (tested end to end in the CLI) | The same, with the Codex plugin commands |
| **Claude Desktop, claude.ai** (chat) | Runs, but not recommended | They cannot load the API keys from environment variables, so the keys would have to be given directly in the chat. That is unsafe and not recommended. Not tested for this skill |
| **Copilot CLI, VS Code** | Installs; not tested | They read the same plugin |
| Claude Desktop or claude.ai chat with no code execution | No | Use the [`report-writing`](../report-writing) skill instead. It has Claude write the report itself, without the quote checks |

The skill can be used in claude.ai and Claude Desktop, but neither can load API keys from
environment variables. They would need the keys typed directly into the chat, which is unsafe
and not recommended. Use instead:

1. **Claude Code**, through the CLI, in Claude Desktop, or through the Claude Code plugin in
   Visual Studio Code.
2. **Codex**, through the ChatGPT application or the Codex plugin in Visual Studio Code.

Both read the API keys from environment variables, which [the next sections](#setting-the-keys-as-environment-variables)
explain how to set.

## Setup

1. **Python 3.11 or later**, and `gaik` with the report-writer extra:

   ```bash
   pip install "gaik[report-writer]"
   ```

2. **For recordings and video, two more things.** Skip them if your sources are documents,
   notes and images only.
   - **ffmpeg**, a program the audio library (pydub) uses to read and convert recordings,
     especially `.mp4` and other video. Without it, normalizing a recording fails.
   - **`audioop-lts`**, a package that Python 3.13 and later need, because they removed the
     standard `audioop` module pydub imports. Without it, normalizing a recording fails with
     `No module named 'pyaudioop'`. Older Pythons do not need it, and `pip` cannot install it
     there, so give it a version condition:

     ```bash
     pip install "audioop-lts; python_version >= '3.13'"
     ```

3. **Pandoc**, only for Word output: [pandoc.org/installing](https://pandoc.org/installing.html).
   When you want Word and Pandoc is missing, the agent tells you and asks whether to install it
   for you (a download into your user folder, with no administrator rights). If you say no, the
   report is Markdown only.
4. **A model provider and its key**, as environment variables (next section). Keys never go in
   the report spec, and do not paste a key into the chat.
5. **The skill itself**: [install it](#installing-the-skill).

### First-time install in one step

Windows, with the recordings and Word output included (run in PowerShell):

```powershell
pip install "gaik[report-writer]" "audioop-lts; python_version >= '3.13'"
winget install --id JohnMacFarlane.Pandoc -e --accept-source-agreements --accept-package-agreements
winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
```

Open a new terminal afterwards so that `pandoc` and `ffmpeg` are on the `PATH`. On macOS,
`brew install pandoc ffmpeg`; on Debian or Ubuntu, `sudo apt install pandoc ffmpeg`.

### Optional installs

You will see a warning such as `Docling core components not available` when the sources are
documents. It is not an error. Install these only if you need them:

- **Docling**, gaik's advanced PDF parser, for richer table and layout extraction from
  complex PDFs: `pip install "gaik[parser]"`.
- **PyTorch**, for GPU-accelerated parsing paths in image- and OCR-heavy flows. Install it from
  [pytorch.org](https://pytorch.org/get-started/locally/) for your hardware.

Without them the skill still reads text PDFs, Word, spreadsheets, text files, images and
recordings.

## Providers and API keys

The workflow works with any provider gaik supports. The one exception is audio and video:
if the sources include recordings that need transcription, the run needs an Azure OpenAI or
OpenAI key. The whole run uses a single provider, so for such a run that provider is Azure
OpenAI or OpenAI for every stage.

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

## Installing the skill

### Claude Code and Codex

```text
/plugin marketplace add GAIK-project/gaik-toolkit
/plugin install gaik-toolkit@gaik-toolkit
```

```bash
codex plugin marketplace add GAIK-project/gaik-toolkit
codex plugin add gaik-toolkit@gaik-toolkit
```

### Claude Desktop and claude.ai

There are two ways. Either gives the agent the skill; the Python setup above is still needed for
it to run.

**A. The whole toolkit as a plugin marketplace (this skill and the others)**

1. Open **Customize → Plugins → Add → Add marketplace → Add from a repository**.
2. Enter `GAIK-project/gaik-toolkit` and choose **Sync**. The client reads
   `.claude-plugin/marketplace.json` at the repository root, which lists one plugin,
   `gaik-toolkit`, and the folder it lives in.
3. On the **Discover** tab, **Add** the `gaik-toolkit` plugin. All its skills become available,
   including this one.
4. Leave **Sync automatically** on, the default, to receive updates when the repository changes.

**B. This skill alone, as an uploaded skill**

1. Get a `.zip` of the skill: download `generate-structured-reports.zip` from the
   [demo app's skills page](https://gaik-demo.2.rahtiapp.fi/skills), or zip the
   `generate-structured-reports` folder yourself with `SKILL.md` directly inside it.
2. Open **Customize → Skills → Add → Upload skill** and choose the `.zip`.
3. An uploaded skill is a copy: it does not update itself. Upload a new `.zip` to update it.

Use A for the full toolkit and automatic updates, and B when you want only this skill.

## Limits

- Scanned PDFs are not read; OCR them first. Pages without a text layer in a mixed PDF are
  reported, and their content is missing from the report.
- Figures inside PDFs and Word files, spreadsheet charts and video frames are not interpreted.
- PowerPoint, .doc, .xls and TIFF files must be converted first.
- Quote checks prove that a quote is in its source, not that the summary reads it correctly or
  that the source is right. The reviewer catches many unsupported statements, not all.
- The run record warns when a report was built from inputs that have since changed; it does not
  notice hand edits to the stages' own files.

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
