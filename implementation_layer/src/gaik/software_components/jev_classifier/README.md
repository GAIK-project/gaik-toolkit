# Jev Classifier

Classify text or documents into your own classes with **Jev**, TypeSafe's System One model.
Jev does not write an answer: it returns the chosen label, a probability for every label and
a confidence. Your code decides what to do with a doubtful case, so a wrong answer is not
silently passed on.

Use it when the classes are known and you want calibrated, fast decisions (routing,
triage, tagging). Use [`doc_classifier`](../doc_classifier/README.md) when you need a written
reason, image input, or the text must stay inside your own LLM provider.

## Installation

```bash
pip install gaik[jev-classifier]
```

## Where the key comes from

GAIK applications do not hold their own TypeSafe key. They call the **gaik-decide**
service with a per-app key, and gaik-decide holds the single TypeSafe key. Pass the
gaik-decide URL as `base_url`:

```python
JevClassifier(api_key=gaik_decide_key, base_url="https://gaik-decide.2.rahtiapp.fi")
```

Inside the `gaik` Rahti namespace use `http://gaik-decide:8080`. With your own TypeSafe key,
leave `base_url` out. The component never reads the environment; the caller passes the key.

**Privacy:** the text is sent to TypeSafe in the United States. Send only what the decision
needs, and no sensitive personal data.

---

## Quick Start

```python
from gaik.software_components.jev_classifier import JevClassifier

classifier = JevClassifier(api_key=key, base_url=url)

result = classifier.classify(
    "Invoice 4412, total 1 240 EUR, due in 30 days",
    classes={
        "invoice": "asks the reader to pay",
        "receipt": "proof that payment was made",
        "contract": "terms two parties agree to",
    },
    instructions="Which kind of business document is this?",
    min_confidence=0.9,
)
print(result["class"], result["confidence"])
# invoice 0.97
```

Give each class a short description. Jev uses it as the meaning of the option, which helps
most when labels are terse or overlap.

---

## API

```python
JevClassifier(
    api_key: str,                  # gaik-decide key, or a TypeSafe key
    base_url: str | None = None,   # gaik-decide root URL; None = TypeSafe directly
    model: str = "jev-1.13.0",     # pinned version; "jev-1.13" is rejected by the API
    timeout: float = 30.0,
    max_retries: int = 3,          # 429 / 5xx, handled by the SDK
)

classifier.classify(text, classes, instructions=None, min_confidence=None,
                    hierarchy=None, max_chars=10_000) -> dict
classifier.classify_many(texts, classes, max_workers=4, **kwargs) -> list[dict]
classifier.classify_file(file_or_dir, classes, **kwargs) -> dict   # PDF, DOCX
```

`classes` is a list of labels or a `{label: description}` mapping (at least two).

**Result**

```python
{
    "class": "invoice",              # after the confidence gate
    "confidence": 0.97,              # how concentrated the probability is
    "probabilities": {"invoice": 0.97, "receipt": 0.02, "contract": 0.01},
    "predicted": "invoice",          # Jev's top label, before the gate
    "model": "jev-1.13.0",
}
```

### Confidence, not just probability

`confidence` is high when nearly all probability landed on one label and low when it spread
across several. It separates answers you can trust from ones you cannot. With
`min_confidence` set, a low-confidence answer becomes `"unknown"`. Start at 0.9 and tune on
labelled examples of your own.

### Reporting a broader label instead

When the classes form a hierarchy, pass `hierarchy={"narrow": "broad"}`. A low-confidence
answer is then reported as the broader label, from the same request:

```python
classifier.classify(
    text,
    classes=["invoice", "receipt", "contract", "nda"],
    min_confidence=0.9,
    hierarchy={"invoice": "financial", "receipt": "financial",
               "contract": "legal", "nda": "legal"},
)
```

### Batches and files

`classify_many` runs requests concurrently and keeps the order. A failed item becomes
`{"class": "unknown", "confidence": 0.0, "error": "..."}` and does not stop the rest.
`classify_file` reads the first `max_chars` characters of PDF and Word files. Images are not
supported because Jev takes text; a scanned PDF without a text layer returns `"unknown"`.

---

## Limits

- 1,200 requests per minute; through gaik-decide 5 million input tokens per key per UTC day.
- gaik-decide accepts 1 to 50,000 characters per text and 2 to 255 labels.
- Probabilities are rounded to two decimals.
- Single label per text. For multi-label tagging use several `Noul` questions with the
  TypeSafe SDK directly.
