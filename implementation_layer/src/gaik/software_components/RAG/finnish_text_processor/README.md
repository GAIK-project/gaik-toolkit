# Finnish Text Processor

Lemmatize Finnish text so a full-text index and a query agree on the same form.

```bash
pip install gaik[finnish-rag]          # pure pip, no system library
```

```python
from gaik.software_components.RAG.finnish_text_processor import FinnishTextProcessor

processor = FinnishTextProcessor(backend="auto")
processor.lemmatize("vahvistetun tilinpäätöksen korjaaminen")
# → ["vahvistettu", "tilinpäätös", "korjata"]
```

---

## Why this exists

Postgres' `finnish` snowball configuration stems inconsistently across a word
family. Measured:

```sql
SELECT to_tsvector('finnish', 'tilinpäätös');      -- 'tilinpäätös'
SELECT to_tsvector('finnish', 'tilinpäätöksen');   -- 'tilinpäätöks'
```

Two different lexemes, so **a search for one does not find a passage containing
the other** — and nothing about the result says a match was missed. Real Finnish
prose is full of these, because the language inflects the stem rather than only
appending to it.

Lemmatizing both the indexed content and the query makes both sides
`tilinpäätös`. On four corpus-shaped Finnish sentences queried with a *different*
inflection than the document used:

| Strategy | Queries that found their document |
| --- | --- |
| `finnish` tsvector + `websearch_to_tsquery` | 1 / 4 |
| `finnish` tsvector + prefix on the lemma | 1 / 4 |
| `simple` tsvector + prefix on the raw term | 0 / 4 |
| **lemmas on both sides** | **4 / 4** |

## Use both sides or neither

This is the one rule. Lemmatizing only the query and matching it against
snowball-stemmed content leaves exactly the mismatch above in place.

```python
# ingest
store_text = processor.to_tsvector_text(chunk)      # → to_tsvector('simple', …)

# query
tsquery = processor.to_tsquery(user_query)          # → to_tsquery('simple', …)
```

Use `'simple'` as the Postgres configuration once you lemmatize: the lemmas are
already normalized, and a second stemming pass on top of them only reintroduces
the inconsistency.

`PgVectorStore` wires this up for you via its `text_processor` argument.

## Prefix matching is a trap for Finnish

`to_tsquery` supports `word:*`, and it is the standard advice for agglutinative
languages. It does not work here, because Finnish alternates the stem rather than
only suffixing it:

| Query lemma | Document form | `lemma:*` matches? |
| --- | --- | --- |
| `kolmikantakauppa` | `kolmikantakaupassa` | no — `kaupp` vs `kaupa` |
| `kirjanpitovelvollisuus` | `kirjanpitovelvollisuutta` | no — `uus` vs `uut` |
| `tilinpäätös` | `tilinpäätöksen` | no — `ös` vs `öks` |

`to_tsquery(..., prefix=True)` is available for callers who want it against an
unstemmed index, but it is not the default and it is not the recommendation.

## Backends

`backend="auto"` tries these in order and takes the first that imports cleanly.
**Check `backend_name` before relying on the result** — the fallback is not a
lemmatizer.

| Backend | Install | Compound splitting | Notes |
| --- | --- | --- | --- |
| `voikko` | `gaik[finnish-rag-voikko]` + system `libvoikko1`, `voikko-fi` | yes | Fastest. Best accuracy. |
| `pyvoikko` | `gaik[finnish-rag]` | yes | Same morphology as a pure-Python FST (~1 MB). Measured identical lemmas to `voikko`. ~2 ms/token, memoised per token. |
| `spacy` | `gaik[finnish-rag]` + `python -m spacy download fi_core_news_md` | no | Weaker on long compounds: left `kirjanpitovelvollisuutta` uninflected and rendered `kirjanpitolaissa` as `kirjanpitolati`. |
| `uralic` | `gaik[finnish-rag]` | no | Downloads its model on first use. |
| `simple` | always | no | Regex + lowercase. **Not a lemmatizer.** Content indexed through it is *less* searchable than snowball-stemmed content. |

`pyvoikko` matters more than its position suggests: **libvoikko is packaged in
neither Red Hat UBI 9 nor EPEL 9**, so on those base images it is the only real
Finnish morphology available at all.

> The PyPI package for the native binding is **`libvoikko`**, not `voikko`. The
> latter installs a `voikko` package exposing `voikko.libvoikko`, so
> `import libvoikko` fails and `VoikkoBackend` silently never loads.

## Compound splitting

```python
FinnishTextProcessor(backend="pyvoikko", decompound=True).lemmatize("vähennysoikeus")
# → ["vähennys", "oikeus"]
```

Parts come from the analyser's **compound structure**, not from `BASEFORM` and
not from `WORDBASES`:

- `BASEFORM` never contains a `+` separator, so splitting it finds nothing to
  split, on every word.
- `WORDBASES` gives *derivational* roots — `vähennysoikeus` becomes `vähetä` +
  `oikea`, a verb and an adjective nobody searches for.

`decompound` widens recall and also widens noise: a short first part like `arvo`
reaches `arvopaperi` and `arvostus` as readily as `arvonlisävero`. Because both
sides are lemmatized consistently, whole-compound matching already works with
`decompound=False` — turn splitting on only if your evaluation set says it helps.

## API

| Method | Returns |
| --- | --- |
| `lemmatize(text)` | `list[str]` of lemmas |
| `to_tsvector_text(text)` | space-separated lemmas, for `to_tsvector` (**ingest**) |
| `expand_query(query)` | space-separated lemmas, for `websearch_to_tsquery` |
| `to_tsquery(text, *, operator="\|", prefix=False)` | a `tsquery` expression, for `to_tsquery` (**query**) |
| `backend_name` | which backend actually loaded |
| `supports_compound_splitting` | whether it can split compounds |

`to_tsquery` defaults to `|` rather than `&` deliberately: conjoining every term
means a nine-word question only matches a passage containing all nine stems,
which on real prose is never, and the keyword arm then contributes nothing
without saying so. `ts_rank_cd` does the discriminating instead.

It also strips tsquery metacharacters from user input, and returns `""` when
nothing usable survives. **`""` is not the same as empty input** — a query made
entirely of stopwords has content and still yields nothing. Treat `""` as "no
keyword arm"; passing it to `to_tsquery()` raises in Postgres.

## Related

- **PgVectorStore** — pass this as `text_processor` and it lemmatizes ingest and
  query through the same pipeline, into a `content_lemmatized` column.
