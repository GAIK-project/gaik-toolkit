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
