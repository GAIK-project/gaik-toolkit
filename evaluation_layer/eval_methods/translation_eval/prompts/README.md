# Blind translation judge: mqm-v1

The exact prompt and JSON schema used in the September 2026 QAD-1 translation
benchmark are available here. These files contain the rubric, with no customer
texts or credentials. The benchmark runners in the private evaluation repository
remain the source of truth; update these copies together if the prompt changes.

| File | Role |
|---|---|
| [mqm-v1.system.txt](mqm-v1.system.txt) | Full Finnish-to-English dental-domain MQM rubric, severity definitions and acceptable paraphrases |
| [mqm-v1.user.txt](mqm-v1.user.txt) | User-message template; substitute `{source}` and `{candidate}` with the two texts |
| [mqm-v1.schema.json](mqm-v1.schema.json) | Structured response: errors, adequacy, fluency and summary |

## Input, output and score

Each call receives the system rubric and the filled user template. It sees one
Finnish source and one English candidate, with no English reference, model name,
vendor or competing translations. The same template judges HY's reference text.
The prompt asks for sentence-by-sentence error annotation and then a separate
fluency check. It accepts meaning-preserving paraphrases and smoothing spoken
fillers. Each error includes a category, severity, quoted source and target spans,
explanation and suggested correction.

This **invented example** illustrates the response; it is not a saved model result:

```text
Finnish source:
Koulutus alkaa maanantaina ja kestää kaksi päivää samassa luokkahuoneessa Helsingissä.

Candidate translation:
The course starts on Monday and lasts five days in the same classroom in Helsinki.
```

```json
{
  "errors": [
    {
      "target_span": "five days",
      "source_span": "kaksi päivää",
      "category": "accuracy/mistranslation",
      "severity": "major",
      "explanation": "The duration changed from two days to five.",
      "correction": "two days"
    }
  ],
  "adequacy": 80,
  "fluency": 100,
  "summary": "The translation is fluent but changes the course duration."
}
```

The scorer assigns critical = 10, major = 5, minor = 1. Here there are 10
Finnish source words and one major error: `5 / 10 × 100 = 50` MQM points per
100 source words. This is a weighted error rate; it can exceed 100 and is not
a percentage. Adequacy and fluency are separate 0–100 ratings and do not set
the chart ranking.

## Validation and aggregation

The benchmark validates categories and severities, then records whether each
quoted span occurs verbatim in its input (also allowing whitespace and quote
normalization). A missing span is flagged in the saved annotation; it is **not
silently removed from the score**. Inspect those flags during human review.

Claude and Gemini judges do not score candidates from their own vendor. Their
rates are converted to a common scale using candidates both judges scored, then
averaged over judged repeats and clips. Clip bootstrap intervals keep that
conversion fixed: they do not establish judge correctness. A native reader
should review a sample of annotations, especially close model rankings.

The benchmark uses direct provider calls with this MQM schema. The toolkit's
[`LLMJudge`](../../../../guidance_layer/docs/software_components/llm_judge.md)
validates structured extraction fields with a different rubric and output
contract. It does not produce these MQM results without an adapter.

See [translation evaluation](../README.md#35-how-the-judging-and-the-charts-were-made)
for the dataset, judge models, repeat coverage and results.
