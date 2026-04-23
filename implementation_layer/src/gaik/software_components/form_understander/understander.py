"""Form field label cleaner."""

from __future__ import annotations

import time
from typing import Literal

from openai import APIError, APITimeoutError, RateLimitError
from pydantic import BaseModel, Field

from gaik.software_components.config import create_openai_client

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
    htmlType: str | None = None
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
        config: configuration dict from ``gaik.software_components.config.get_openai_config``.
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
        self.client = create_openai_client(self.config)

    def clean_labels(
        self,
        fields: list[dict] | list[InputField],
        language_hint: LanguageHint | None = None,
    ) -> dict[str, str]:
        """
        Return a mapping of each input id → short readable label.

        Unknown ids in the LLM response are dropped; empty labels are dropped;
        labels longer than 60 chars are truncated so the caller can rely on
        a bounded payload size.
        """
        safe_fields: list[InputField] = []
        for f in fields:
            if isinstance(f, InputField):
                safe_fields.append(f)
            else:
                safe_fields.append(InputField(**f))
        if not safe_fields:
            return {}

        # Compose the user message. System prompt ships as-is; the user
        # message contains the language hint (if any) plus a compact listing
        # of the fields.
        lines: list[str] = []
        if language_hint:
            lines.append(f"Output language hint: {language_hint}.")
        lines.append("Fields:")
        for f in safe_fields:
            chunks = [f"- id={f.id!r}", f"label={f.raw!r}"]
            if f.type:
                chunks.append(f"type={f.type}")
            if f.htmlType:
                chunks.append(f"htmlType={f.htmlType}")
            if f.parent:
                # Cap parent snippet so the prompt stays small on huge forms.
                snippet = f.parent if len(f.parent) <= 200 else f.parent[:200]
                chunks.append(f"parent={snippet!r}")
            lines.append(" ".join(chunks))
        user_prompt = "\n".join(lines)

        def _call():
            return self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=LabelMapping,
                temperature=0,
                top_p=1.0,
                seed=12345,
                timeout=30,
            )

        resp = _with_retries(_call)
        parsed: LabelMapping = resp.choices[0].message.parsed

        known_ids = {f.id for f in safe_fields}
        result: dict[str, str] = {}
        for entry in parsed.entries:
            if entry.id not in known_ids:
                continue
            label = entry.label.strip()
            if not label:
                continue
            result[entry.id] = label[:60]
        return result
