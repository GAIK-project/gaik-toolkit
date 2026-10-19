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

## Installing the skill
For **Running in Claude Desktop --> Claude Code**:

1. Get a `.zip` of the skill: download `generate-structured-reports.zip` from the
   [demo app's skills page](https://gaik-demo.2.rahtiapp.fi/skills), or zip the
   `generate-structured-reports` folder yourself with `SKILL.md` directly inside it.
2. Open **Customize → Skills → Add → Upload skill** and choose the `.zip`.

For running with **Claude Code in VS Code, or CLI**, save the skill folder in ~/.claude/skills at user or project level. 

For running with **Codex (ChatGPT Codex, CLI, or Codex plugin in VS Code)**, save the skill folder in ~/.agents/skills at user or project level. 

Before running the skill, set the API keys on your computer as environment variables (for example in PowerShell with the
`setx` command, see [Setting the keys as environment variables](#setting-the-keys-as-environment-variables)).

Then, the skill can be invoked as follows:

```text
Use the generate-structured-reports skill to write a project status report from these meeting recordings and the risk register. 
```

When the skill starts for the first time, it installs all the dependencies it needs. You
only need Python 3.11 or later and an API key (see [Providers and API keys](#providers-and-api-keys)).

The dependencies required by the skill at the time of first run include gaik's report writer module (`gaik[report-writer]`), `ffmpeg`, `audioop-lts`, `pandoc`, and some optional dependencies such as `docling`, and `PyTorch`. 

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
