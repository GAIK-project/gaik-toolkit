# Finnish full-text search

Read this before indexing Finnish text, when a Finnish word that is visibly in a document
is not found, or when choosing a lemmatizer backend.

## Contents
- Why the snowball stemmer is not enough
- Lemmatize both sides
- Choosing and pinning a backend
- Prefix matching and compounds
- Long queries flood the lemma arm
- Hyphenated words
- Text hygiene
- Queries in another language
- Backfilling a lemma column
- The embedding model matters more here

## Why the snowball stemmer is not enough

Postgres' `finnish` configuration stems inconsistently across one word family:

```sql
SELECT to_tsvector('finnish', 'tilinpäätös');     -- 'tilinpäätös'
SELECT to_tsvector('finnish', 'tilinpäätöksen');  -- 'tilinpäätöks'
```

Two lexemes, so a search for one form cannot find a passage containing the other however
it is phrased. On Finnish prose, where the same term appears in a different case in almost
every sentence, that is the common case. Nothing reports the miss — the vector arm quietly
carries the query.

## Lemmatize both sides

The gain comes from the index and the query agreeing on a form, not from either side
alone. Measured on four sentences queried in a different inflection than the document used:

| Index | Query | Found |
|---|---|---|
| `finnish` tsvector | `websearch_to_tsquery` | 1/4 |
| `finnish` tsvector | prefix on the lemma | 1/4 |
| `simple` tsvector | prefix on the raw term | 0/4 |
| lemmas | lemmas | **4/4** |

Index the lemmas with the `simple` configuration: they are already normalized, and stemming
them again reintroduces the inconsistency they were produced to remove. With gaik, pass a
`FinnishTextProcessor` as `PgVectorStore(text_processor=..., fts_language="simple")` — it
writes a `content_lemmatized` column at ingest and lemmatizes each query through the same
processor. Without gaik, write a second tsvector column at ingest from
`processor.to_tsvector_text(text)` and query it with `to_tsquery('simple',
processor.to_tsquery(query))`.

`processor.to_tsquery()` returns `""` when nothing usable survives, which a query of pure
stopwords does. Passed on, `to_tsquery('simple', '')` does not raise: it logs a NOTICE and
returns an empty query that matches nothing, so the arm goes quiet without an error. Treat
`""` as "no keyword arm" and fall back to the other mode explicitly.

## Choosing and pinning a backend

| Backend | Install | Notes |
|---|---|---|
| `voikko` | `gaik[finnish-rag-voikko]` + the libvoikko system library | fastest; splits compounds |
| `pyvoikko` | `gaik[finnish-rag]` | the same morphology as pure Python; runs anywhere |
| `spacy` | `gaik[finnish-rag]` + `python -m spacy download fi_core_news_md` | measured 2/4 above: left `kirjanpitovelvollisuutta` inflected and produced `kirjanpitolati` |
| `uralic` | `gaik[finnish-rag]` | pure Python, lightweight |
| `simple` | always | regex tokenizer + lowercase — **not a lemmatizer**; refuse it |

Pin the backend by name. `backend="auto"` tries voikko first, so it picks the native
library on a machine that has it and something else in a container that does not —
libvoikko is packaged in neither Red Hat UBI 9 nor EPEL 9 — and the index and the query end
up lemmatized differently. The arm then matches nothing, which reads exactly like a corpus
without an answer. Check `processor.backend_name` at startup and refuse `simple`: content
indexed through it is less searchable than the snowball column it would replace.

## Prefix matching and compounds

`term:*` is the usual advice for agglutinative languages, and against Finnish inflection it
fails, because Finnish alternates the stem rather than only adding suffixes:

- `kolmikantakauppa` never reaches `kolmikantakaupassa` (`kaupp` against `kaupa`);
- `kirjanpitovelvollisuus` never reaches `kirjanpitovelvollisuutta` (`uus` against `uut`);
- `uudistus` never reaches `uudistuksesta`.

Prefix matching does help one thing on a snowball index: reaching compounds that *start*
with the query word. The stemmer turns `yötyölisä` into `yötyölis`, which a query for
`yötyö` never matches but `yötyö:*` does.

`decompound=True` (gaik's default) splits compounds into parts on both sides. With lemmas on
both sides whole compounds already match, and splitting widens noise: `arvonlisävero`
yields `arvo`, which reaches `arvopaperi` and `arvostus` just as readily. Start with
`decompound=False` and turn it on only if a measurement says so. The index and the query
must use the same setting, so changing it means re-indexing.

## Long queries flood the lemma arm

Lemmas collapse every inflection, so each term matches more. A 25-word question lemmatized
to about 20 OR-joined terms, matched 78–79% of one corpus, and the arm's ranking carried so
little information that it displaced the vector arm inside the fusion: Hit@1 fell from
3/5 to 2/5. On short queries the same arm matched two to five times as many documents as
snowball did.

So the lemma arm is a short-query improvement. For long input, split the request into 3–6
short topic queries (an LLM does this well), search each, and fuse the document rankings
with RRF — the regime where the arm wins. Dropping terms that match a large share of the
corpus is the other fix; measure the effect on both query sets.

## Hyphenated words

Postgres' parser splits a hyphenated word, and `to_tsquery('simple', 'sote-uudistus:*')`
becomes the phrase `'sote-uudistus':* <-> 'sote':* <-> 'uudistus':*`, which does not match
`sote-uudistuksesta`. Quoting does not help. Emit an OR group of the whole word and its
parts instead: `('sote-uudistus':* | 'sote':* | 'uudistus':*)`.

## Text hygiene

- **No `unaccent`.** ä/a and ö/o are different letters: `tähti`/`tahti`, `sää`/`saa`,
  `vähä`/`vaha`.
- **Strip zero-width characters** (U+200B and friends) at ingest and at query time. Editors
  paste them in; Postgres does not treat them as whitespace, so
  `to_tsvector('finnish', 'kirjanpidossa')` stems to `kirjanpido` while the same word with
  one appended stays unstemmed and never matches.
- **Decode strictly.** Files from Finnish systems are often cp1252 whatever their extension
  says. Reading with `errors="replace"` does not fail — it silently turns every ä and ö into
  `�`, which wrecks embeddings and stemming alike. Try UTF-8 strictly, then cp1252.

## Queries in another language

Postgres full-text cannot cross languages: `websearch_to_tsquery('finnish', 'giving
feedback')` yields `'giving' & 'feedback'`, which no Finnish passage contains. An English
question against a Finnish index took the keyword arm from 33.7% to 5.4% recall@15.

Translate into the corpus language as a **full question**. Translating into a list of
search terms helped the keyword arm (5.4% → 20.7%) but wrecked the vector arm and finished
at 47.8%, 14 points below not translating at all; a translated question reached 66.3%. The
other working pattern keeps the original query for a multilingual embedding and sends
translated keywords to the keyword arm only. Detect the query language cheaply first
(ä/ö, common suffixes) so Finnish queries skip the LLM call.

## Backfilling a lemma column

An existing corpus needs its lemma column filled without re-embedding. The backfill must
use the same backend and `decompound` setting as the query path — both should come from one
setting — or the arm silently stops matching. Budget time from a warm run: `pyvoikko`
memoises per token, so the first batch is several times slower than the steady rate
(about 665 chunks a minute on one corpus).

## The embedding model matters more here

On one Finnish corpus an open multilingual embedding model running inside the container
beat a paid English-first default on recall@15 (75.0% against 71.7%), MRR (0.557 against
0.480) and latency. Benchmark two or three candidates on your own query set before
choosing; the leaderboard order did not survive the move to Finnish.
