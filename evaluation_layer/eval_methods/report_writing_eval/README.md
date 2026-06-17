# Report Writing Evaluation

Quality assessment pipeline for AI-generated reports using an LLM-as-judge approach that identifies issue types, assigns severity levels, and produces a structured quality score.

---

## 1. Evaluation Metrics

### 1.1 Evaluation Criteria

The evaluation assesses generated reports against four quality criteria. For each criterion, identified issues are classified by severity level (low, medium, high).

| Criterion | What it measures |
|-----------|-----------------|
| **Factual Error** | Information in the report that is incorrect or inconsistent with the source material |
| **Missing Section** | A structurally required section of the report is entirely absent |
| **Required Elements Missing** | Within an existing section, specific mandatory content elements are absent |
| **Clarity Issues** | Language that is ambiguous, poorly structured, or difficult to understand |

### 1.2 Severity Levels

Each identified issue is assigned one of three severity levels:

| Severity | Description | Examples |
|----------|-------------|---------|
| **High** | The issue significantly affects the usability or correctness of the report | Incorrect date or location, mandatory section absent, key finding missing, critical passage unclear |
| **Medium** | The issue reduces report quality but does not invalidate the core content | Important supporting detail wrong, recommended section absent, paragraph unclear |
| **Low** | The issue is a minor imperfection with minimal impact on usability | Slight wording inaccuracy, optional element missing, minor ambiguity |

### 1.3 Scoring

Reports receive a quality score from 0 to 10. The score starts at 10 and deductions are applied based on identified issues and their severity:

```text
Score = 10 - Σ(deduction per issue)
Score is capped at 0 (minimum)
```

**Deduction weights:**

| Severity | Deduction per issue |
|----------|-------------------|
| High | 2.0 points |
| Medium | 1.0 point |
| Low | 0.5 points |

**Score interpretation:**

| Score | Assessment |
|-------|-----------|
| 9–10 | Excellent — report meets all requirements with only minor issues |
| 7–8 | Good — report is usable with a few medium-severity issues to correct |
| 5–6 | Fair — report requires revision before use |
| 3–4 | Poor — significant issues affect correctness or completeness |
| 0–2 | Unacceptable — fundamental problems; report must be regenerated |

---

## 2. Evaluation Tools / Code

### 2.1 Evaluation Approach

Report quality is assessed using an **LLM-as-judge** workflow:

1. The generated report and the source material (transcript, input documents) are passed to an LLM judge
2. The judge is prompted to review the report against each of the four criteria
3. For each issue found, the judge records the criterion type, severity level, a brief description, and the affected section
4. The evaluator script aggregates the issues, computes the weighted score, and writes a structured report

This approach enables automated, repeatable quality assessment without human reviewers for each run, while remaining interpretable — every deduction is traceable to a specific identified issue.

### 2.2 Python Dependencies

Main packages needed for an LLM-as-judge evaluation script:
- `openai` or `anthropic` — for the LLM judge API call
- `pydantic` — for structured issue output from the judge
- `python-dotenv` — for API key management

### 2.3 Evaluation Data

Each evaluation requires:
- **Generated report** — the AI-produced report to be assessed (plain text or structured JSON)
- **Source material** — the original inputs used to generate the report (transcript, documents, field notes)
- **Report template** — the expected structure and required elements for the report type

---

## 3. Results

---

## 4. Performance Issues (Errors)

### 4.1 Factual Errors

| Severity | Common Cause | Example |
|----------|-------------|---------|
| **High** | Hallucination or source misread | Wrong incident date, incorrect location name, fabricated action |
| **Medium** | Paraphrase that changes meaning | "No injuries" reported as "minor injuries" |
| **Low** | Minor inaccuracy with no practical impact | Slightly wrong time, imprecise quantity |

Root causes: low-quality transcription upstream, insufficient grounding in source material, LLM hallucination when source content is sparse.

### 4.2 Missing Sections

| Severity | Common Cause | Example |
|----------|-------------|---------|
| **High** | Required structural section omitted | Incident report missing the "Actions Taken" section entirely |
| **Medium** | Recommended section skipped | Summary or conclusion absent |
| **Low** | Optional section not generated | Appendix or reference list absent |

Root causes: prompt does not specify the full required report structure; model truncates output for long reports.

### 4.3 Required Elements Missing

| Severity | Common Cause | Example |
|----------|-------------|---------|
| **High** | Key field absent within a section | Date, observer name, or severity flag missing from incident header |
| **Medium** | Supporting detail absent | Consequence description present but no recommended follow-up action |
| **Low** | Secondary supporting detail absent | Optional photo reference or document link absent |

Root causes: source material lacks the information (upstream capture gap); extraction or synthesis step did not propagate the value into the report.

### 4.4 Clarity Issues

| Severity | Common Cause | Example |
|----------|-------------|---------|
| **High** | Critical information is ambiguous or misleading | It is unclear whether an incident was a near-miss or an actual event |
| **Medium** | A section is difficult to follow | Run-on sentences, contradictory statements, or unexplained jargon |
| **Low** | Minor wording issue | Awkward phrasing that does not affect comprehension |

Root causes: LLM generation without a style guide; mixed register (formal + colloquial); technical jargon not defined for the target audience.

---

## 5. Improvement Strategies

### 5.1 High-Level Improvement Strategies

- Strengthen the report generation prompt with explicit structure requirements
- Provide a filled reference example report in the prompt to guide format and style
- Improve upstream data quality (transcription, extraction) to reduce factual errors
- Apply a post-generation validation pass using the same LLM-as-judge before delivering the report

### 5.2 Mapping Table: Issues → Improvement Strategies

| Issue type | Improvement strategy |
|-----------|----------------------|
| Factual errors (high) | Strengthen source grounding in the generation prompt; add explicit "only use information from the source" constraint |
| Factual errors (medium/low) | Add a post-generation fact-check pass against the original source |
| Missing sections | Include the full required section list in the generation prompt; use a report template as a structural guide |
| Required elements missing | List mandatory elements per section explicitly in the prompt; consider a fill-in-the-blanks template |
| Clarity issues (high) | Add style instructions to the prompt (target audience, tone, sentence length); use a shorter generation loop with section-by-section review |
| Clarity issues (medium/low) | Add a post-generation rewriting pass focused on clarity |

---

## Reproduction Notes (Usage Guide)

### Evaluation Workflow

The LLM-as-judge evaluation follows these steps:

1. **Prepare inputs** — collect the generated report, its source material, and the report template defining required sections and elements
2. **Run the judge** — pass all three to an LLM judge with a structured prompt that asks it to identify issues by criterion type and severity
3. **Parse the output** — extract the structured list of issues from the judge's response (using Pydantic or JSON schema output)
4. **Compute the score** — apply deduction weights and subtract from 10
5. **Write the report** — save a structured evaluation report listing all issues, their severity, affected section, and the final score

### Expected Output Format

```
========== REPORT QUALITY EVALUATION ==========

Report:  [report filename or ID]
Score:   8.5 / 10

========== ISSUES FOUND ==========

[MEDIUM] Factual Error — Section: Incident Description
  The reported time (14:30) does not match the source transcript (15:30).

[LOW]    Clarity Issue — Section: Actions Taken
  The sentence "the matter was addressed accordingly" is vague.

========== SUMMARY ==========

Total issues:    2
  High:          0
  Medium:        1
  Low:           1

Deductions:      1.5 points
Final Score:     8.5 / 10
```

---

## Integration with GAIK Toolkit

### Evaluating GAIK Report Generation Workflows

The evaluation is designed to assess reports generated by GAIK's knowledge synthesis workflows. Example integration:

```python
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from gaik.software_components.extractor import DataExtractor, SchemaGenerator, get_openai_config

config = get_openai_config(use_azure=True)

# 1. Generate the report using GAIK workflow
# (transcription → extraction → report synthesis)
generated_report = Path("reports/incident_report_001.txt").read_text(encoding="utf-8")
source_material = Path("transcripts/incident_001.txt").read_text(encoding="utf-8")

# 2. Run LLM-as-judge evaluation
# TODO: call evaluate(generated_report, source_material, report_template)

# 3. Save evaluation output
# Path("evaluations/incident_report_001_eval.json").write_text(...)
```

### Supported Use Cases

This evaluation methodology applies to the following GAIK report generation workflows:

- **Construction site report generation** — Multi-source inspection and progress reports combining documents, images, and transcripts

---

## Installation & Setup

### 1. Install Dependencies

```bash
cd evaluation_layer/eval_methods/report_writing_eval
pip install openai pydantic python-dotenv
```

### 2. Configure API Access

```bash
export OPENAI_API_KEY="your-api-key"
```

PowerShell:

```powershell
$env:OPENAI_API_KEY = "your-api-key"
```

---

## Related Resources

- **LLM-as-Judge Validation**: [guidance_layer/website/content/docs/toolkit/evals/llm-judge.mdx](../../../guidance_layer/website/content/docs/toolkit/evals/llm-judge.mdx)
- **Extraction Evaluation**: [../extraction_eval/README.md](../extraction_eval/README.md)
- **Evaluation Methods Overview**: [../README.md](../README.md)
- **Project Website**: [gaik.ai](https://gaik.ai)
- **GitHub**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
