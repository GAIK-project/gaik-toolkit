"""Form field label cleaner."""

from __future__ import annotations

import re
import time
import unicodedata
from typing import Literal

from openai import APIError, APITimeoutError, RateLimitError
from pydantic import BaseModel, Field

from gaik.software_components.llm.base import ProviderClient
from gaik.software_components.llm.factory import build_compat_client
from gaik.software_components.llm.parameters import normalize_chat_kwargs
from gaik.software_components.source_material import SourceMaterial, source_material_messages

LanguageHint = Literal["fi", "en"]

SYSTEM_PROMPT = (
    "You are a form-field label cleanup assistant. "
    "Given a list of form fields (id, raw label, type, optional parent HTML snippet), "
    "return a mapping from each id to a short human-readable label "
    "(≤ 40 characters, no trailing punctuation). "
    "Use Finnish if the language hint is 'fi' or if the snippets contain Finnish words "
    "(ä, ö, å, 'syntymä', 'postiosoite', 'kansalaisuus' etc.); English otherwise. "
    "NEVER invent a field — return an entry for every id you receive, preserving the id exactly. "
    "If the raw label is already clean (no colons, no _ctlN path segments), "
    "return it trimmed as-is. "
    "If it is cryptic (ASP.NET paths, generated names), infer the likely meaning "
    "from the parent HTML snippet. When ambiguous, prefer a short noun phrase "
    "over a guess (e.g. 'Field 3' is better than a wrong label)."
)


class InputField(BaseModel):
    """Input row for FormUnderstander.clean_labels."""

    id: str
    raw: str
    type: str | None = None
    htmlType: str | None = None  # noqa: N815 - public input field used by browser clients
    parent: str | None = None


class LabelEntry(BaseModel):
    """One id → cleaned label pair. We use a list of these instead of a
    free-form ``dict[str, str]`` because OpenAI structured outputs do not
    support open-ended maps (``additionalProperties``)."""

    id: str
    label: str


class LabelMapping(BaseModel):
    """LLM response schema."""

    entries: list[LabelEntry] = Field(default_factory=list)


class CleanedLabel(BaseModel):
    """The label a person sees, with the label the page itself gave the field.

    The page's labels and HTML steer the names the model returns, so a field can be
    shown as something it is not. Show ``original`` next to ``label`` when ``changed``
    is true, so the person can tell what the page said.
    """

    id: str
    label: str
    """The cleaned label, at most 60 characters; the page's own label, cut to 60, when
    the model returned none for the id."""
    original: str
    """The raw label as the page gave it, trimmed."""
    changed: bool
    """True when ``label`` has other words than ``original`` (case, spacing and
    sentence punctuation aside). A page label only cut to 60 characters is not a
    change; see ``truncated``."""
    truncated: bool = False
    """True when ``label`` is the page's own label cut to 60 characters: show
    ``original`` too, since the cut may drop meaning."""


MAX_LABEL_CHARS = 60
_SENTENCE_PUNCTUATION = re.compile(r"[:;!?]|\.(?=\s|$)")


def _visible(text: str) -> str:
    """``text`` without invisible format characters (soft hyphens, bidi controls).

    They are taken out of every label gaik returns, so the label a person sees is the
    one that was compared: a bidi control could otherwise show words in another order.
    """
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


def _words(text: str) -> str:
    """``text`` without what a cleanup may change: case, spacing, sentence punctuation.

    Only canonical Unicode differences are ignored (NFC), so a superscript or a ß stays
    what it is, and only ``: ; ! ?`` and a sentence-ending ``.`` are dropped, so "1.000"
    and "1,000", "-5" and "5", or a required-field ``*`` still differ.
    """
    text = _visible(unicodedata.normalize("NFC", text))
    return " ".join(_SENTENCE_PUNCTUATION.sub(" ", text).split()).lower()


def _same_words(a: str, b: str) -> bool:
    """The same words, case, spacing and sentence punctuation aside ("Name:", "name")."""
    return _words(a) == _words(b)


def _with_retries(call, tries: int = 3):
    for i in range(tries):
        try:
            return call()
        except (RateLimitError, APITimeoutError, APIError):
            if i == tries - 1:
                raise
            time.sleep(2**i)


class FormUnderstander:
    """
    Turn cryptic form-field identifiers into readable labels.

    Args:
        config: Provider config from ``get_llm_config`` or legacy ``get_openai_config``.
        model: optional model name override. Defaults to ``config["model"]``.

    Example:
        >>> from gaik.software_components.config import get_openai_config
        >>> cfg = get_openai_config(use_azure=True)
        >>> u = FormUnderstander(config=cfg)
        >>> u.clean_labels(
        ...     fields=[{"id": "a", "raw": "FieldInput:FieldRepeater:_ctl1:InputTextRow"}],
        ...     language_hint="fi",
        ... )
        {'a': 'Etunimi'}
    """

    def __init__(self, config: dict, model: str | None = None):
        self.config = config
        self.model = model or self.config["model"]
        self.client = build_compat_client(self.config)

    def clean_labels(
        self,
        fields: list[dict] | list[InputField],
        language_hint: LanguageHint | None = None,
    ) -> dict[str, str]:
        """
        Return a mapping of each input id → short readable label.

        Unknown ids in the LLM response are dropped; empty labels are dropped;
        labels longer than 60 chars are truncated so the caller can rely on
        a bounded payload size. To show the page's own label beside the cleaned
        one, use :meth:`describe_labels`.
        """
        return self._clean(fields, language_hint)

    def describe_labels(
        self,
        fields: list[dict] | list[InputField],
        language_hint: LanguageHint | None = None,
    ) -> list[CleanedLabel]:
        """Each field's cleaned label next to the label the page gave it, in input order.

        The page's labels and HTML steer the names the model returns, so a field can be
        shown as something it is not. ``changed`` tells which labels the model rewrote;
        show their ``original`` beside them. A field the model returned no label for
        keeps its page label (``changed`` false).
        """
        safe_fields = [f if isinstance(f, InputField) else InputField(**f) for f in fields]
        ids = [f.id for f in safe_fields]
        repeated = sorted({i for i in ids if ids.count(i) > 1})
        if repeated:
            # The model answers per id, so two fields with one id would get one label.
            raise ValueError(f"field ids must be unique; repeated: {repeated}")
        cleaned = self._clean(safe_fields, language_hint)
        described = []
        for f in safe_fields:
            original = _visible(f.raw).strip()
            label = cleaned.get(f.id, original[:MAX_LABEL_CHARS])
            truncated = len(original) > MAX_LABEL_CHARS and _same_words(
                label, original[:MAX_LABEL_CHARS]
            )
            described.append(
                CleanedLabel(
                    id=f.id,
                    label=label,
                    original=original,
                    changed=not (_same_words(label, original) or truncated),
                    truncated=truncated,
                )
            )
        return described

    def _clean(
        self,
        fields: list[dict] | list[InputField],
        language_hint: LanguageHint | None,
    ) -> dict[str, str]:
        safe_fields: list[InputField] = []
        for f in fields:
            if isinstance(f, InputField):
                safe_fields.append(f)
            else:
                safe_fields.append(InputField(**f))
        if not safe_fields:
            return {}
        if language_hint not in (None, "fi", "en"):
            raise ValueError(f"language_hint must be 'fi', 'en' or None, not {language_hint!r}")

        # The labels and HTML come from the page, so the listing goes in a data block,
        # apart from the rules; the language hint is the caller's and stays outside.
        lines: list[str] = []
        for f in safe_fields:
            chunks = [f"- id={f.id!r}", f"label={f.raw!r}"]
            if f.type:
                chunks.append(f"type={f.type!r}")
            if f.htmlType:
                chunks.append(f"htmlType={f.htmlType!r}")
            if f.parent:
                # Cap parent snippet so the prompt stays small on huge forms.
                snippet = f.parent if len(f.parent) <= 200 else f.parent[:200]
                chunks.append(f"parent={snippet!r}")
            lines.append(" ".join(chunks))
        material = SourceMaterial()
        hint = f"Output language hint: {language_hint}.\n" if language_hint else ""
        messages = source_material_messages(
            SYSTEM_PROMPT, hint + "Fields:\n" + material.wrap("\n".join(lines), label="form fields")
        )

        def _call():
            if isinstance(self.client, ProviderClient):
                return self.client.chat_parsed(
                    model=self.model,
                    messages=messages,
                    response_format=LabelMapping,
                    temperature=0,
                )
            response = self.client.beta.chat.completions.parse(
                model=self.model,
                messages=messages,
                response_format=LabelMapping,
                **normalize_chat_kwargs(
                    self.model, {"temperature": 0, "top_p": 1.0, "timeout": 30}, config=self.config
                ),
            )
            return response.choices[0].message.parsed

        parsed: LabelMapping | None = _with_retries(_call)
        if parsed is None:
            raise ValueError("The model did not return a structured label mapping")

        known_ids = {f.id for f in safe_fields}
        result: dict[str, str] = {}
        for entry in parsed.entries:
            if entry.id not in known_ids:
                continue
            label = _visible(entry.label).strip()
            if not label:
                continue
            result[entry.id] = label[:MAX_LABEL_CHARS]
        return result
