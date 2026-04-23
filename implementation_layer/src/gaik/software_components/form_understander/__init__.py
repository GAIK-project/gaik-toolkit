"""
Form Understander

Maps cryptic form-field identifiers (e.g. ASP.NET
``FieldInput:FieldRepeater:_ctl1:InputTextRow``) to short human-readable
labels using a small LLM call. Useful when rendering form field lists in
user interfaces, where the raw identifiers give the user no clue what each
field represents.

Main class:
    - FormUnderstander: clean a batch of field labels in one call.

Usage:
    from gaik.software_components.config import get_openai_config
    from gaik.software_components.form_understander import FormUnderstander

    cfg = get_openai_config(use_azure=True)
    understander = FormUnderstander(config=cfg)
    mapping = understander.clean_labels(
        fields=[
            {"id": "a", "raw": "FieldInput:FieldRepeater:_ctl1:InputTextRow"},
            {"id": "b", "raw": "Etunimet"},
        ],
        language_hint="fi",
    )
    # -> {"a": "Etunimi", "b": "Etunimet"}
"""

from .understander import FormUnderstander, InputField, LabelEntry, LabelMapping

__all__ = [
    "FormUnderstander",
    "InputField",
    "LabelEntry",
    "LabelMapping",
]
__version__ = "0.1.0"
