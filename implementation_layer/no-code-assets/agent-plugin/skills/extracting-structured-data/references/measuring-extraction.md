# Measuring extraction quality

Read this when comparing two extraction configurations, when someone asks whether a change
helped, or when there is no labelled data and measurement seems blocked.

## Contents
- Measure stability before you have ground truth
- Rules that keep a comparison honest
- Reading a zero correctly
- What gaik provides
- Recording enough to reproduce a number

## Measure stability before you have ground truth

Comparing repeats against each other needs no correct answer. A folder of unlabelled
documents is enough to answer "do we get the same result every time", which is in practice
the question being asked most of the time.

This is a large lever, because building ground truth is slow and expensive, and nothing is
being measured while waiting for it. Stability metrics are available the same day.

The caveat that makes it usable: **stability alone rewards silence.** A configuration that
leaves the deep fields empty is perfectly repeatable, because empty is always the same
empty. In one measured case a single-call branch looked flawlessly stable on governance
documents purely because it never filled the nested levels; the cascade that replaced it
did not *create* instability, it **exposed** what the empty fields had been hiding. Always
read a stability number beside a completeness number.

## Rules that keep a comparison honest

**Five repeats minimum.** Without repeats there is no spread, without spread there is no
noise floor, and without a noise floor a difference is not a small result — it is not a
result at all.

**The denominator must not move with the numerator.** Averaging a loss rate only over the
documents that lost something makes two runs incomparable and can invert the ranking: five
losses in one document prints 100%, six losses across six documents prints 20%. Fix the
denominator to every (document, field) pair with a non-empty expectation, times the number
of repeats, whether anything happened or not. Lock it with a test.

**A failed document scores zero and stays in the sample.** Dropping it lets a pipeline
raise its own average by crashing on the hardest inputs.

**Failure is a result, not a missing row.** A refused request, a truncated output, and a
confidently wrong answer all score zero but are three different findings needing three
different fixes. Averaged together, the information is gone. Classify and report them
separately.

**Address rows by identifier, not position.** Insert a row at the top of a table and every
position-based path shifts, so two nearly identical answers look completely different. Key
on an identifying field wherever one exists.

**Cell agreement and byte agreement say different things.** One repeat returning `1000.0`
where four returned `1000` is cell agreement 1.0 and byte comparison 0.60. Both numbers are
correct and both are needed: the first is about quality, the second about whether outputs
can be diffed.

**A published leaderboard row is a claim, not a baseline.** One reproduction attempt landed
79.34 against a published 87.87, and the gap was almost entirely 21 documents that could
not be submitted at all. Compare within your own run.

## Reading a zero correctly

A run with an F1 of 0.0 but a cell agreement of 1.0 is **not an unstable model**. It is a
document that produced nothing — a quota rejection, a timeout, a refused request. When
output did arrive it was identical every time, which is exactly what the agreement number
is reporting.

This cost one real, publishable-looking false finding: a newer model appeared markedly less
stable than its predecessor, which would have made a tidy result. In fact 8 of 180
documents had received rate-limit responses. On a clean rerun the spread was zero.

**Read the failure column before calling anything unstable.**

The upstream cause is usually error classification. A rate-limit response passing through a
layer that sits *below* the provider's own error handling arrives unclassified and gets
re-raised as permanent; the runner does not retry, the documents score zero, and in
aggregate it is indistinguishable from model variance. Every layer that calls a model
classifies its own errors — a shared classifier is cheap, and its absence buys a wrong
result. The related subtlety in a branching pipeline: transient errors *must* propagate up
to the runner or a quota spike vanishes as one silently missing level, while other errors
must not discard the whole document. Those are two different rules.

## What gaik provides

```python
from gaik.software_components.evaluators import ExtractionEvaluator

result = ExtractionEvaluator().evaluate_dataset(dataset, extracted_outputs)
result.metrics    # precision, recall, f1, hallucination_rate, n_correct/n_expected
```

`extracted_outputs` is one dict per item **in the same order** as `dataset.items`, and each
`item.expected` must be a dict. The aggregate is micro-averaged, which is the behaviour you
want here — it keeps the denominator fixed across runs instead of averaging per-document
averages.

Related components: `LLMJudge` for rubric scoring and schema-agnostic hallucination
detection, `LLMJudgePanel` for majority vote across judges with an agreement metric,
`compare_pairwise` for A/B with position-bias mitigation, and `BatchEvaluationRunner` to
apply a pipeline over a dataset with `on_error="skip"`.

Note that `on_error="skip"` removes failures from the output. That is convenient for
getting a run finished and wrong for scoring — reinstate the skipped items as zeros before
computing a metric, or the average silently rewards crashing.

## Recording enough to reproduce a number

Stamp every run with the model, the region, a hash of the corpus, the commit, and whether
the working tree was dirty. A run made from a dirty tree cannot be reproduced from its
commit, and nothing else in the output would ever reveal that.

Two environment traps that corrupt results while looking like model failures:

- `Path.write_text()` without an explicit `encoding` uses the platform codepage, which on
  Windows is cp1252 and raises on characters document parsers routinely emit. A crashed
  write scores as a failed extraction. Always pass `encoding="utf-8"` and run with
  `PYTHONIOENCODING=utf-8`.
- Test helpers that build objects by setting attributes instead of going through the real
  constructor stop covering the constructor the moment configuration gains a field — and
  they can stop covering it *silently*. Build through the real constructor.
