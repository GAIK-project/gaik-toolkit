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
order, each field's cleaned `label`, the `original` label the page gave it, and
`changed`, which is true when the model used other words (case, spacing and punctuation
aside). Show `original` beside `label` where `changed` is true:

```python
for field in understander.describe_labels(fields, language_hint="fi"):
    shown = f"{field.label} (page: {field.original})" if field.changed else field.label
```

A field the model returned no label for keeps its page label. The page's labels and
HTML reach the model in a `<source_material>` block, apart from the rules, so a label
that reads like an instruction stays data.
