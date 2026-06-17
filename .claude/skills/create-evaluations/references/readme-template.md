# README Template — Implementation Layer Evaluation

This document defines the canonical structure for `evaluation_layer/eval_methods/{component}_eval/README.md`.

Follow `transcription_eval/README.md` as the gold-standard reference. The sections below are required; mark any section that has no user-provided content as `_N/A — to be completed._`

---

## File Header

```markdown
# {{Component Display Name}} Evaluation

{{One-sentence description of what the evaluation measures.}}
```

No frontmatter. Plain Markdown only.

---

## Section Structure

All top-level sections use `##` with a number prefix. Subsections use `###` with a dotted number (`1.1`, `1.2`, etc.).

---

### `## 1. Evaluation Metrics`

#### `### 1.1 List of Metrics`

Bullet list of metric names. Example:

```markdown
The current evaluation uses the following metrics:

- {{Metric 1}}
- {{Metric 2}}
- {{Metric 3}}
```

#### `### 1.2 Metric Descriptions`

One sub-subsection (`####`) per metric using this pattern:

```markdown
#### {{Metric Name}}

- Definition:
  - {{One-sentence plain-language definition.}}
- Formula:

\`\`\`text
{{FORMULA = components / total * 100%}}
\`\`\`

- Components:
  - `{{var}}` = {{meaning}}
  - `{{var}}` = {{meaning}}
- Business interpretation:
  - {{Why this metric matters for the use case.}}
  - {{What a high/low value means in practice.}}
- Reference values:

| {{Metric}} Range | Assessment | Typical Applications |
|-----------------|-----------|---------------------|
| **< X%**        | Excellent  | {{context}}         |
| **X–Y%**        | Good       | {{context}}         |
| **> Y%**        | Poor       | {{context}}         |

*Source: {{citation or "No universal thresholds; lower is better."}}*
```

If no reference thresholds exist: `- Reference values: No universal thresholds; lower is better.`

---

### `## 2. Evaluation Tools / Code`

#### `### 2.1 Python Scripts`

Bullet list. One bullet per script:

```markdown
- `{{script_name.py}}`
  - {{What the script does — one sentence.}}
  - {{Key input → output description.}}
```

#### `### 2.2 Python Dependencies`

```markdown
Defined in `requirements.txt`.

Main packages:
- `{{package}}` for {{purpose}}
- `{{package}}` for {{purpose}}
```

#### `### 2.3 Reproducibility Inputs`

```markdown
Example files in this folder include:
- `data/{{file}}` — {{description}}
- `data/{{file}}` — {{description}}
```

---

### `## 3. Evaluations / Comparisons`

#### `### 3.1 Evaluation Setup / Context`

```markdown
Evaluation context:
- Domain: {{domain, e.g. Finnish dental webinars}}
- Language: {{language}}
- Content: {{type of content evaluated}}
- Goal: {{what the evaluation aims to measure}}

Models/methods compared:
- {{model or method 1}}
- {{model or method 2}}
```

#### `### 3.2 Performance Comparison Table`

Markdown table. Rows = models/methods, columns = metrics.

```markdown
| Model | {{Metric 1}} | {{Metric 2}} | {{Metric 3}} |
|-------|-------------|-------------|-------------|
| {{model}} | {{value}} | {{value}} | {{value}} |
```

Bold the best value per column: `**14.57%**`

#### `### 3.3 Key Findings / Observations`

```markdown
- Best {{metric}} in this benchmark: `{{model}}` with `{{value}}`
- {{Observation about what works well or why.}}
- {{Observation about what enhancement/method improves.}}
```

---

### `## 4. Performance Issues (Errors)`

#### `### 4.1 List of Common Error Categories`

Group errors into sub-categories. Each sub-category uses a bold heading and a Markdown table:

```markdown
#### {{Error Group Name}} (e.g. "Model-level errors")

| Error Type | Description | Examples | Why / Fix Strategy |
|-----------|-------------|----------|--------------------|
| **{{Error}}** | {{description}} | {{example}} | {{strategy}} |
```

Include at least:
- Errors that require a better model/approach
- Errors fixable via post-processing
- Acceptable / "live with" errors (if any)

#### `### 4.2 Side-by-Side Input-Output Examples` *(optional)*

Show annotated examples if relevant. Use bold for error-marked tokens.

---

### `## 5. Improvement Strategies`

#### `### 5.1 High-Level Improvement Strategies`

Prose + bullet list:

```markdown
Main improvement directions:
- {{strategy}}
- {{strategy}}
```

#### `### 5.2 Mapping Table: Performance Issues → Improvement Strategies`

```markdown
| Performance issue / error | Improvement strategy |
|--------------------------|----------------------|
| {{error type}}           | {{strategy}}         |
```

---

### `## Reproduction Notes (Usage Guide)`

One sub-section per script/workflow. Each sub-section:

```markdown
### Running {{task description}}

{{Brief description of what this command does.}}

\`\`\`bash
python {{script.py}} <arg1> <arg2> [options]
\`\`\`

**Example:**
\`\`\`bash
python {{script.py}} \\
  {{arg1_value}}/ \\
  {{arg2_value}}/
\`\`\`

**Outputs:**
- {{output description}}
- {{output description}}

**Sample Output:**
\`\`\`
{{representative console output block}}
\`\`\`
```

No numbered prefix on this section (it was `##` without number in the transcription pattern — match that).

---

### `## Integration with GAIK Toolkit`

Two subsections:

```markdown
### Evaluating GAIK {{Component}} Component

Use these evaluation scripts to assess GAIK `{{ClassName}}` output quality:

\`\`\`python
from gaik.software_components.{{component}} import {{ClassName}}
from pathlib import Path

# 1. Run component with GAIK
{{component_usage_code}}

# 2. Save output for evaluation
{{save_code}}

# 3. Evaluate against ground truth
# python {{script.py}} reference/ output/ reports/
\`\`\`

### Supported Use Cases

This evaluation suite supports:
- **{{Use Case}}** — {{brief description}}
- **{{Use Case}}** — {{brief description}}
```

---

### `## Installation & Setup`

```markdown
### 1. Install Dependencies

\`\`\`bash
cd evaluation_layer/eval_methods/{{component}}_eval
pip install -r requirements.txt
\`\`\`

**Dependencies:**
- `{{package}}==X.Y.Z` — {{purpose}}

### 2. Configure API Access

{{Env var instructions if LLM calls are needed, or omit if not.}}
```

---

### `## Related Resources`

```markdown
- **GAIK {{Component}} Component**: [guidance_layer/docs/software_components/{{component}}.md](link)
- **Main README**: [README.md](../../../README.md)
- **Evaluation Methods Overview**: [../README.md](../README.md)
- **Project Website**: [gaik.ai](https://gaik.ai)
- **Documentation**: [https://gaik-project.github.io/gaik-toolkit/](https://gaik-project.github.io/gaik-toolkit/)
```

---

## Formatting Conventions

| Rule | Detail |
|------|--------|
| Section numbering | Top-level `## 1.`, subsections `### 1.1`, metrics `#### Metric Name` |
| Code blocks | Use ` ```text ` for formulas, ` ```bash ` for CLI, ` ```python ` for code |
| Table alignment | Left-align all columns; bold best/notable values with `**value**` |
| N/A sections | `_N/A — to be completed._` as the sole content of that section body |
| Horizontal rules | `---` used only between major top-level sections (optional, used in transcription pattern) |
| Encoding | UTF-8; non-ASCII characters in examples are fine |
