# Relevance Gate

Tell "the corpus answered this" apart from "here are the nearest neighbours".

Pure Python. No database, no model, no dependencies — it ships with `gaik`.

```python
from gaik.software_components.RAG.relevance_gate import RelevanceGate

gate = RelevanceGate(floor=0.60)                 # cosine distance
hits = store.search_semantic(query_embedding, top_k=20)

if not gate.is_answerable(hits, key=lambda hit: hit[1]):
    return "Nothing in the library covers this."
```

---

## Why a result count is not evidence

A vector index answers every query. Ask it for nonsense and it returns its
nearest neighbours, ranked, with scores — a page that looks exactly like a page
of real answers. Measured on one production corpus:

| Query | Results returned |
| --- | --- |
| `zzzqqq blorptastic wibble` | **24** |
| a real domain question | **12** |

So anything that reasons from `len(results)` has the signal backwards. What does
discriminate is the distance to the *closest* match: real questions land near
something, unanswerable ones land far from everything.

This matters because it is what makes an honest "we don't cover that" possible.
Without it, an off-topic request comes back as a confident answer assembled from
whatever happened to be nearest.

## Calibrate — don't copy the number

The floor is a reading off **one** embedding model against **one** corpus. Change
either and take it again.

```python
reading = RelevanceGate.calibrate(
    answerable=[0.264, 0.41, 0.562],      # best score per query the corpus covers
    unanswerable=[0.637, 0.72, 0.866],    # best score per query it does not
)
print(reading)
# separated: answerable ≤ 0.562, unanswerable ≥ 0.637, margin 0.075 → floor 0.600

gate = RelevanceGate(floor=reading.floor) if reading.separated else None
```

When the populations overlap there is no threshold, and `calibrate` says so
rather than splitting the difference:

```text
OVERLAPPING by 0.090: answerable reaches 0.710 while unanswerable reaches
0.620 — no threshold separates them
```

A number that splits an overlap looks like a measurement and rejects real
queries. `separated is False` means the caution has to come from somewhere else.

**Put ordinary off-topic questions in the `unanswerable` set, not only
gibberish.** Gibberish is easy to separate. A well-formed question about a
subject the corpus has never heard of is what a user actually types, and it is
the case that decides whether your floor is worth anything.

## `None` means "no opinion", not "irrelevant"

A keyword-only search produces no distances at all. Treating that as "far away"
turns the gate into a permanent refusal on exactly the mode that has nothing to
say. So `None` scores pass, and `best()` returns `None` when every score is
missing.

An **empty** result list is different, and is never answerable.

## API

| Method | Purpose |
| --- | --- |
| `is_answerable(results, *, key=None)` | Did this query find anything the corpus covers? |
| `best(results, *, key=None)` | Closest score, or `None` when there is nothing to judge |
| `passes(score)` | Is one score on the relevant side of the floor? |
| `filter(results, *, key=None)` | Drop individual results outside the floor, keeping order |
| `RelevanceGate.calibrate(answerable, unanswerable, *, lower_is_better=True)` | Read a floor off two labelled populations |

`lower_is_better=True` for distances (cosine distance, L2); `False` for
similarities (cosine similarity, `ts_rank_cd`). There is no default that suits
both, because getting it backwards inverts the gate silently.

`key` lets the gate work on whatever shape your retriever returns:

```python
gate.is_answerable(hits, key=lambda hit: hit[1])          # (Document, score) pairs
gate.is_answerable(rows, key=lambda r: r.vector_distance) # your own objects
```

Do not use `filter()` to decide whether the corpus answered at all. A trimmed
list that happens to be non-empty is a different question from `is_answerable`.

## Related

- **PgVectorStore** — `search_semantic` has a `threshold` argument; this component
  is how you work out what to set it to.
- **Ranker** — fuses and reorders results. Gate first, then rank: fusing a page of
  nearest neighbours produces a confidently ordered page of nearest neighbours.
