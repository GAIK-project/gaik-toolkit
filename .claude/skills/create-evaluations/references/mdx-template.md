# MDX Template — Website Evaluation Page

This document defines the canonical structure for `guidance_layer/website/content/docs/evaluation-layer/{component}-eval.mdx`.

Follow `transcription-eval.mdx` and `extraction-eval.mdx` as references. Sections below are required; mark missing content as `_N/A — to be completed._`

---

## Frontmatter

```yaml
---
title: {{Component Display Name}} Evaluation
description: {{One-sentence description for SEO and navigation — match this to the index.mdx entry.}}
---
```

No other frontmatter keys. Do not add `sidebar`, `order`, or `icon` fields.

---

## Section Order

All sections use `##` (H2). No section numbering. Order is fixed:

1. The Problem
2. How We Evaluate
3. Benchmarking Results
4. Error Classification
5. Real-World Applications
6. Quality Considerations
7. Getting Started

Each section is separated by `---`.

---

## Section Details

### `## The Problem`

Opens the page. Explains the business challenge the component addresses and why inaccuracy matters.

Pattern:
```markdown
## The Problem

{{2–3 sentence business context. What the component does and why accuracy is critical.}}

Key challenges include:
- **{{Challenge}}** — {{one-sentence explanation}}
- **{{Challenge}}** — {{one-sentence explanation}}
- **{{Challenge}}** — {{one-sentence explanation}}
```

Optional: add a short concrete example (a mini bulleted form) to make challenges tangible. See `extraction-eval.mdx` lines 16–25 for an example.

Tone: business-first, no formulas here.

---

### `## How We Evaluate`

Explains the methodology at a conceptual level. Use `###` subsections for each main concept.

Pattern:
```markdown
## How We Evaluate

{{1–2 sentence overview of the evaluation approach.}}

### {{Key Concept 1, e.g. "Understanding Word Error Rate (WER)"}}

{{Explanation of the metric/method.}}

- **{{Component/type}}** — {{what it measures}} (*example in italics*)
- **{{Component/type}}** — {{what it measures}}

**{{Metric}} Interpretation:**
- **Below X%** — {{meaning for this use case}}
- **X–Y%** — {{meaning}}
- **Above Y%** — {{meaning}}

### {{Key Concept 2}}

{{Explanation.}}
- **{{Improvement type}}** — {{what it does}}
```

Keep formulas out of this section unless essential. This section should be readable by a non-technical stakeholder.

---

### `## Benchmarking Results`

Presents empirical data. Always include a `### Key Findings` sub-section.

Pattern:
```markdown
## Benchmarking Results

{{1–2 sentences describing the benchmark setup — domain, language, content type.}}

### {{Model/Approach}} Performance

{{Optional: reference an image if one exists.}}

![{{Alt text}}](/images/{{image-name}}.png)

{{Optional: Markdown table. Rows = models/approaches, columns = metrics.}}

| Model | {{Metric 1}} | {{Metric 2}} | Assessment |
|-------|-------------|-------------|-----------|
| {{model}} | {{value}} | {{value}} | {{label}} |

Bold the best row value: `**14.57%**`

### Key Findings

- **{{Insight}}** — {{explanation}}
- **{{Insight}}** — {{explanation}}
- **{{Insight}}** — {{explanation}}
```

If no benchmark data: `_N/A — to be completed._` for the table; Key Findings can still include known expectations or hypotheses.

---

### `## Error Classification`

Classifies errors by how they can be addressed. Use `###` for each error group. Within each group, use bold **Problem** and **Impact** sub-headings.

Pattern (matches extraction-eval.mdx):
```markdown
## Error Classification

### {{Error Group 1, e.g. "Field Confusion"}}

**Problem**: {{description of what goes wrong}}
- {{specific example or symptom}}
- {{specific example or symptom}}

**Impact**: {{business consequence}}

### {{Error Group 2}}

**Problem**: {{description}}
- {{example}}

**Impact**: {{consequence}}
```

Minimum two groups. Recommended structure (adapt to the component):
1. Errors requiring a better model / approach (fundamental)
2. Errors fixable via post-processing or prompt tuning
3. Acceptable / "live with" errors (if any)

---

### `## Real-World Applications`

Lists GAIK use cases where this evaluation method applies.

Pattern:
```markdown
## Real-World Applications

{{Component}} evaluation supports these GAIK use cases:

- **{{Use Case}}** — {{one-sentence description}}
- **{{Use Case}}** — {{one-sentence description}}
- **{{Use Case}}** — {{one-sentence description}}
```

Reference existing GAIK use cases where possible (incident reporting, construction diary, meeting documentation, content localization, etc.).

---

### `## Quality Considerations`

Framed as questions or considerations the reader should think about for their own deployment. Bold lead + one-sentence explanation.

Pattern:
```markdown
## Quality Considerations

When evaluating {{component}} quality for your specific use case, consider:

**{{Consideration}}** — {{one-sentence explanation of the trade-off or question to ask.}}

**{{Consideration}}** — {{explanation.}}

**{{Consideration}}** — {{explanation.}}
```

Minimum four considerations. Examples: accuracy vs. cost, domain specificity, acceptable error rate, volume vs. quality.

---

### `## Getting Started`

Numbered list of practical steps to run the evaluation. Ends with a GitHub link.

Pattern:
```markdown
## Getting Started

To evaluate {{component}} quality in your own context:

1. {{Step: data preparation}}
2. {{Step: run the evaluation}}
3. {{Step: interpret results}}
4. {{Step: iterate/improve}}
5. {{Step: monitor in production}}

For technical implementation details and evaluation tools, visit the [GAIK GitHub repository](https://github.com/GAIK-project/gaik-toolkit/tree/main/evaluation_layer/eval_methods/{{component}}_eval).
```

Keep steps 4–6; do not over-specify implementation details here (those belong in the README).

---

## MDX Component Rules

| Component | When to use |
|-----------|-------------|
| `<Callout type="warn">` | **Only** for Coming Soon stubs. Never on a full evaluation page. |
| `<Callout type="info">` | Optional: for helpful sidebars or cross-references to related pages. |
| All other components | Do not use (`<Card>`, `<Tabs>`, `<Steps>`, etc. are not used in this section). |

---

## Formatting Conventions

| Rule | Detail |
|------|--------|
| Section separator | `---` between every `##` section |
| Bold | `**term**` for lead terms in lists and considerations; `**value**` for best results in tables |
| Italic | `*example text*` for inline examples of extracted/transcribed content |
| Code blocks | Not used on this page except inside Getting Started steps if unavoidable |
| Links | Relative links for internal toolkit pages: `[Title](/evaluation-layer/page)`. Absolute for GitHub. |
| Images | `![Alt text](/images/filename.png)` — image file must exist under `guidance_layer/website/public/images/` |
| N/A sections | `_N/A — to be completed._` as the sole line of that section body |
| Tone | Business-first; explain why before how; accessible to non-technical stakeholders |

---

## index.mdx Entry Format

When a full page is created, add this block to `index.mdx` inside the "Available Evaluation Methods" section, before the first `<Callout type="warn">` stub:

```markdown
### {{Component Display Name}} Evaluation

{{One-sentence description — must match the MDX `description` frontmatter exactly.}}

[View {{Component Display Name}} Evaluation →](/evaluation-layer/{{component}}-eval)

---
```

If a Coming Soon stub for this component already exists in `index.mdx`, replace the entire stub (the `###` heading + `<Callout>` block + `---`) with this entry.

---

## meta.json Update

Insert the new page slug after the last fully-implemented page slug and before the first stub slug:

```json
{
  "title": "Evaluation Methods",
  "pages": [
    "index",
    "transcription-eval",
    "extraction-eval",
    "llm-judge",
    "llm-judge-benchmark",
    "{{component}}-eval",   ← insert here
    "rag-eval",
    "report-writing-eval",
    "translation-eval"
  ]
}
```

The slug must exactly match the `.mdx` filename (without extension).
