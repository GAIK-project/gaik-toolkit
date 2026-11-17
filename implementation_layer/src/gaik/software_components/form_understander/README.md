# FormUnderstander

Convert cryptic form identifiers into short labels while preserving the input identifiers.

```python
from gaik.software_components.form_understander import FormUnderstander
from gaik.software_components.llm import get_llm_config

understander = FormUnderstander(get_llm_config("openai", model="gpt-6-luna"))
labels = understander.clean_labels(
    [{"id": "first_name", "raw": "FieldInput:_ctl1:Name"}],
    language_hint="en",
)
```

Pass any shared provider config that supports structured output, including Azure, Google, Anthropic, Aitta and optional LiteLLM. Legacy `get_openai_config()` dictionaries remain supported. An optional `model=` argument overrides the configured model.

`clean_labels()` accepts dictionaries or `InputField` instances. It drops unknown identifiers and blank labels, trims whitespace, and limits each returned label to 60 characters. Empty input returns an empty dictionary without an inference call.

## Show the page's own label

The labels and HTML come from the page, and they steer the names the model returns, so
a field can be shown as something it is not. `describe_labels()` returns, in input
order, each field's cleaned `label`, the `original` label the page gave it, `changed`
and `truncated`:

```python
for field in understander.describe_labels(fields, language_hint="fi"):
    shown = field.label
    if field.changed or field.truncated:
        shown = f"{field.label} (page: {field.original})"
```

- `changed` is true when the model used other words. Case, spacing and the sentence
  punctuation `: ; ! ?` and a sentence-ending `.` do not count; superscripts, `ß`,
  `1.000` versus `1,000`, signs and a required-field `*` do.
- `truncated` is true when `label` is the page label cut to 60 characters, which may
  drop the end of a long question.
- `changed` says only that the words differ, not that the new label is right. For a
  cryptic generated id it is always true and `original` tells the person little; a
  label steered through the page's HTML looks the same as a correct one.
- Invisible format characters (soft hyphens, bidi controls) are removed from both
  `label` and `original`, so what is compared is what is shown. Escape the labels for
  the place you show them (HTML, a terminal) as with any page text.

`label` is at most 60 characters, like `clean_labels()`. Field ids must be unique (a
repeated id raises `ValueError`, since the model answers per id), and `language_hint` is
`"fi"`, `"en"` or `None`. A field the model returned no label for keeps its page label.
The page's labels and HTML reach the model in a `<source_material>` block, apart from
the rules; that lowers the chance that a label written as an instruction steers the
model, it does not remove it.
