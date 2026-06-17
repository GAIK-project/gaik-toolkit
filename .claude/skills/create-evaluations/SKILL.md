---
name: create-evaluations
description: >-
  Creates evaluation documentation for a GAIK component in both locations:
  evaluation_layer/eval_methods/{component}_eval/ (README + optional script stubs)
  and guidance_layer/website/content/docs/evaluation-layer/{component}-eval.mdx
  (full user-facing page). Also updates index.mdx and meta.json to register the new page.
argument-hint: "[component-name] [evaluation context: metrics, results, methodology, error analysis, use cases]"
---

# Create Evaluations

Generates evaluation documentation for a GAIK component in two mirrored locations following the established pattern of `transcription_eval` and `extraction_eval`.

**Requires user-provided context** — the user must supply the evaluation details (metrics, results, methodology, errors, use cases) as part of their message or as attached content. This skill does not run evaluations itself; it documents them.

---

## What this skill creates

| File | Action |
|------|--------|
| `evaluation_layer/eval_methods/{component}_eval/README.md` | Create (or promote stub to full) |
| `evaluation_layer/eval_methods/{component}_eval/requirements.txt` | Create if scripts are requested |
| `evaluation_layer/eval_methods/{component}_eval/*.py` | Create script stubs if requested |
| `guidance_layer/website/content/docs/evaluation-layer/{component}-eval.mdx` | Create (or promote stub to full) |
| `guidance_layer/website/content/docs/evaluation-layer/index.mdx` | Update: add new entry, remove Coming Soon stub |
| `guidance_layer/website/content/docs/evaluation-layer/meta.json` | Update: insert page before remaining stubs |

---

## Workflow

### Phase 1 — Context Parsing

1. Read the component source at `implementation_layer/src/gaik/software_components/{component}/` to understand what the component does, its inputs, outputs, and configuration options.
2. If a stub README exists at `evaluation_layer/eval_methods/{component}_eval/README.md`, read it.
3. If a stub MDX exists at `evaluation-layer/{component}-eval.mdx`, read it.
4. Map the user-provided context against the **required sections** for both output files (see `references/readme-template.md` and `references/mdx-template.md` for the full section lists).
5. For each required section where no context was provided, ask the user:
   > "No content was provided for **[Section Name]** (e.g. benchmarking results / error taxonomy / CLI usage). Do you want to supply it now, or continue and mark it N/A?"
   - If the user supplies content → incorporate it before generating files.
   - If the user skips → that section gets `_N/A — to be completed._` as its body.
6. Ask once: **"Should I also generate Python evaluation script stubs, or README + website content only?"**

### Phase 2 — Outline

Present a two-column outline to the user:

```
README sections:          MDX sections:
1. Evaluation Metrics     1. The Problem
2. Tools / Code           2. How We Evaluate
3. Results                3. Benchmarking Results
4. Error Classification   4. Error Classification
5. Improvement Strategies 5. Real-World Applications
6. Reproduction / Usage   6. Quality Considerations
7. Integration snippet    7. Getting Started
8. Installation & Setup
9. Related Resources

Populated: [list sections that have content]
N/A:       [list sections that will be marked N/A]
Scripts:   [yes / no]
```

### Phase 3 — Plan Review *(never skip)*

Present the outline and wait for explicit approval before writing any files. Adjust based on feedback. Do not start Phase 4 until the user confirms.

### Phase 4 — Generate Content

Run all sub-steps in order. Do not commit.

**4a — Implementation Layer README**

Follow the structure in `references/readme-template.md`. Key rules:
- Use `##` for numbered top-level sections (`## 1. Evaluation Metrics`, `## 2. Evaluation Tools / Code`, etc.)
- Use `###` for subsections (`### 1.1 List of Metrics`, `### 3.2 Performance Comparison Table`, etc.)
- Each metric gets: Definition, Formula (code block), Components, Business interpretation, Reference values table
- Results section has a Markdown table with model names as rows and metric columns
- Improvement strategies section has a mapping table: `| Performance issue | Improvement strategy |`
- Integration section has a code snippet using the actual component's Python API
- Sections with no user-provided content → `_N/A — to be completed._`

**4b — Python Script Stubs** (only if user said yes in Phase 1)

Create one stub per logical evaluation step following the pattern below. Add a `requirements.txt`.

```python
"""
{component}_eval — {purpose of this script}.

Usage:
    python {script_name}.py <arg1> <arg2>
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main(arg1: str, arg2: str) -> None:
    # TODO: implement evaluation logic
    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arg1", help="...")
    parser.add_argument("arg2", help="...")
    args = parser.parse_args()
    main(args.arg1, args.arg2)
```

**4c — Website MDX Page**

Follow the structure in `references/mdx-template.md`. Key rules:
- Frontmatter: `title` (display name) and `description` (one sentence, matches index entry)
- Section order: The Problem → How We Evaluate → Benchmarking Results → Error Classification → Real-World Applications → Quality Considerations → Getting Started
- Tone: business-first (why it matters), then technical detail
- Challenges in "The Problem" → bullet list with bold lead term
- Results → Markdown table + **Key Findings** bullet list below it
- Error categories use bold **Problem** / **Impact** sub-headings (see extraction-eval pattern)
- Quality Considerations: bold question/statement + one-sentence explanation per item
- Getting Started: numbered list of 4–6 steps, ending with GitHub repo link
- Do **not** use `<Callout type="warn">` — that is only for Coming Soon stubs
- N/A sections: use `_N/A — to be completed._`

**4d — Update `index.mdx`**

In the **Output Evaluation Methods** section, under the **Available Methods** list, append the new entry after the last existing `### … Evaluation` entry. If any Coming Soon `<Callout type="warn">` stubs are present, insert the entry immediately before the first one instead (before its preceding `---`):

```markdown
### {Component Display Name} Evaluation

{One-sentence description matching the MDX `description` frontmatter.}

[View {Component Display Name} Evaluation →](/evaluation-layer/{component}-eval)

---
```

If a Coming Soon stub for this component already exists (`### {Name}` + Callout), replace that entire stub block with the new entry.

**4e — Update `meta.json`**

Insert `"{component}-eval"` in the `pages` array within the Output Evaluation Methods group — after the `"---Output Evaluation Methods---"` separator and after the last existing method slug (before any remaining stub slug, if present). The page key must match the `.mdx` filename exactly (minus `.mdx`).

### Phase 5 — Verification Summary

After writing all files, print:

```
Files created / modified:
  ✓ evaluation_layer/eval_methods/{component}_eval/README.md  (N lines)
  ✓ guidance_layer/website/content/docs/evaluation-layer/{component}-eval.mdx  (N lines)
  ✓ guidance_layer/website/content/docs/evaluation-layer/index.mdx  (updated)
  ✓ guidance_layer/website/content/docs/evaluation-layer/meta.json  (updated)
  [✓ script stubs if generated]

Sections marked N/A: [list or "none"]

To verify:
  cd guidance_layer/website && pnpm dev
  → /evaluation-layer/{component}-eval  (confirm page renders)
  → /evaluation-layer               (confirm index entry and sidebar position)
```

---

## Hard Rules

- **Never skip Phase 3.** Always wait for explicit approval before writing files.
- **Never overwrite a full README or MDX** (i.e. one that already has real content, not just a stub) without the user explicitly confirming they want to replace it.
- **`meta.json` page key must exactly match the `.mdx` filename** (minus `.mdx`). A mismatch silently breaks sidebar navigation.
- **Full pages must not use `<Callout type="warn">`** — reserved for Coming Soon stubs only.
- **Do not commit.** Leave all changes staged-but-uncommitted so the user can review with `git diff`.
- **Script stubs are scaffolds, not implementations.** Never fabricate evaluation logic or invent metric results.
- **Do not invent results.** If no benchmarking data was provided and the user said N/A, leave the results table as a placeholder, not made-up numbers.

---

## References

- `references/readme-template.md` — canonical implementation README structure with all section headings, subsection numbering, and formatting conventions
- `references/mdx-template.md` — canonical website MDX structure with frontmatter, section order, MDX component rules, and link conventions

Pattern references (read these when in doubt):
- `evaluation_layer/eval_methods/transcription_eval/README.md` — most complete README example
- `guidance_layer/website/content/docs/evaluation-layer/transcription-eval.mdx` — most complete MDX example
- `guidance_layer/website/content/docs/evaluation-layer/extraction-eval.mdx` — second MDX example (simpler results section)
