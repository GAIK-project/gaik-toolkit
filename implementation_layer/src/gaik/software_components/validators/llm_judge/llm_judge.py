"""Multi-provider LLM-as-judge validator for structured-extraction outputs."""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from typing import Any, Literal

from .pricing import compute_judge_cost_usd
from .prompts import build_system_prompt, build_user_prompt
from .schema import (
    JudgeUsage,
    Severity,
    ValidationFlag,
    ValidationResult,
    ValidationRubric,
)

logger = logging.getLogger(__name__)

ModelProvider = Literal["openai", "azure", "anthropic", "google"]

DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-5.4-mini",
    "azure": "gpt-5.4-mini",
    "anthropic": "claude-haiku-4-5-20251001",
    "google": "gemini-3-flash-preview",
}


class LLMJudge:
    """LLM-as-judge validator.

    Feeds page images plus an extractor's JSON output to a chosen vision-capable
    LLM and asks it to flag fields that don't match the document. Returns a
    structured result so the caller can render UI badges, gate downstream
    confirmations, etc.

    The judge is provider-agnostic but reuses the configuration helpers from
    :mod:`gaik.software_components.parsers.multimodal_parser.config` so consumers
    only need to set up provider env-vars once.

    Scoring modes are controlled per-call via ``rubric.scoring_mode``:

    - ``"severity"`` (default): three-class flagging only (ok/suspect/wrong),
      no integer Likert score. Backward-compatible with v1.
    - ``"likert_1_5"``: integer Likert 1-5 + severity. ~30 % better
      human-correlation than continuous scales (HuggingFace cookbook).
    - ``"additive"``: 1 point per ``rubric.evaluation_aspect`` satisfied.

    Args:
        model_provider: ``"openai"`` | ``"azure"`` | ``"anthropic"`` | ``"google"``.
            Default ``"google"`` (best F1 in our internal judge benchmark).
        model: Model id (or Azure deployment name). Defaults to a
            sensible per-provider value.
        use_azure: Only meaningful when ``model_provider == "openai"`` — switches
            the OpenAI client between standard OpenAI (``False``) and Azure
            OpenAI (``True``).
        use_vertexai: Only meaningful when ``model_provider == "google"`` —
            switches the Google client between Vertex AI (``True``, recommended)
            and Generative Language API (``False``).
        max_tokens: Upper bound on the judge's response length.
        reasoning_effort: Optional ``"low" | "medium" | "high"`` for reasoning
            models (gpt-5.4, gpt-5.5). Ignored for non-reasoning models.
    """

    def __init__(
        self,
        model_provider: ModelProvider = "google",
        model: str | None = None,
        use_azure: bool = True,
        use_vertexai: bool = True,
        max_tokens: int = 4096,
        reasoning_effort: str | None = None,
    ) -> None:
        if model_provider not in ("openai", "azure", "anthropic", "google"):
            raise ValueError(
                f"Unknown model_provider: {model_provider!r}. "
                "Expected one of openai/azure/anthropic/google."
            )
        self.model_provider = model_provider
        self.model = model or DEFAULT_MODELS[model_provider]
        self.use_azure = use_azure
        self.use_vertexai = use_vertexai
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort

    # ── Public API ────────────────────────────────────────────────

    def validate(
        self,
        source_pages: list[bytes],
        extracted: list[dict] | dict,
        rubric: ValidationRubric | None = None,
    ) -> ValidationResult:
        """Run one judge pass and return parsed flags + usage.

        Args:
            source_pages: PNG-encoded page images (one entry per page).
            extracted: The extractor's structured output. Free-form JSON;
                the toolkit does not enforce a schema. Lists of items work
                naturally with ``item_index`` flags.
            rubric: Optional rubric. ``rubric.scoring_mode`` selects between
                severity-only, integer Likert, and additive scoring.

        Returns:
            :class:`ValidationResult` with flags, raw text, and usage.
        """
        if not source_pages:
            raise ValueError("source_pages must contain at least one page image")

        rubric = rubric or ValidationRubric()
        system_prompt = build_system_prompt(rubric.scoring_mode)
        user_prompt = build_user_prompt(extracted, rubric)

        t0 = time.perf_counter()
        raw_text, input_tokens, output_tokens = self._dispatch(
            source_pages, user_prompt, system_prompt
        )
        duration_s = time.perf_counter() - t0

        flags = parse_judge_flags(raw_text)
        usage = JudgeUsage(
            provider=self.model_provider,
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            duration_s=duration_s,
            cost_usd=compute_judge_cost_usd(self.model, input_tokens, output_tokens),
        )
        return ValidationResult(flags=flags, raw_judge_text=raw_text, usage=usage)

    # ── Provider callers ──────────────────────────────────────────

    def _dispatch(
        self,
        source_pages: list[bytes],
        user_prompt: str,
        system_prompt: str,
    ) -> tuple[str, int, int]:
        """Route to the right ``_call_*`` for ``self.model_provider``."""
        provider_call = {
            "openai": self._call_openai,
            "azure": self._call_openai,
            "anthropic": self._call_anthropic,
            "google": self._call_google,
        }[self.model_provider]
        return provider_call(source_pages, user_prompt, system_prompt)

    def _call_openai(
        self,
        source_pages: list[bytes],
        user_prompt: str,
        system_prompt: str,
    ) -> tuple[str, int, int]:
        # Use the multimodal_parser config helpers — single source of truth
        # for env-var parsing across the toolkit.
        from gaik.software_components.parsers.multimodal_parser.config import (
            create_openai_client,
            get_openai_config,
        )

        config = get_openai_config(use_azure=self.use_azure)
        client = create_openai_client(config)

        image_parts = [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{base64.b64encode(p).decode()}",
                },
            }
            for p in source_pages
        ]
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [{"type": "text", "text": user_prompt}, *image_parts],
            },
        ]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
        }
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort

        resp = client.chat.completions.create(**kwargs)
        text = resp.choices[0].message.content or ""
        usage = resp.usage
        return (
            text,
            getattr(usage, "prompt_tokens", 0) or 0,
            getattr(usage, "completion_tokens", 0) or 0,
        )

    def _call_anthropic(
        self,
        source_pages: list[bytes],
        user_prompt: str,
        system_prompt: str,
    ) -> tuple[str, int, int]:
        # Reuse the toolkit's existing claude client (Foundry on Azure or direct API).
        from gaik.software_components.parsers.multimodal_parser.config import (
            create_claude_client,
            get_claude_config,
        )

        config = get_claude_config(use_azure=self.use_azure)
        client = create_claude_client(config)
        image_parts = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.b64encode(p).decode(),
                },
            }
            for p in source_pages
        ]
        resp = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        *image_parts,
                        {"type": "text", "text": user_prompt},
                    ],
                }
            ],
        )
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )
        return text, resp.usage.input_tokens, resp.usage.output_tokens

    def _call_google(
        self,
        source_pages: list[bytes],
        user_prompt: str,
        system_prompt: str,
    ) -> tuple[str, int, int]:
        from google import genai
        from google.genai import types

        if self.use_vertexai:
            client = genai.Client(
                vertexai=True,
                project=os.environ["GOOGLE_VERTEXAI_PROJECT"],
                location=os.environ.get("GOOGLE_VERTEXAI_LOCATION", "global"),
            )
        else:
            api_key = os.environ.get("GOOGLE_GEMINI_API_KEY") or os.environ.get(
                "GOOGLE_API_KEY"
            )
            if not api_key:
                raise RuntimeError(
                    "No Google credentials. Set GOOGLE_VERTEXAI_PROJECT (+ "
                    "GOOGLE_APPLICATION_CREDENTIALS) and use_vertexai=True, "
                    "or set GOOGLE_GEMINI_API_KEY."
                )
            client = genai.Client(api_key=api_key)

        parts: list[Any] = [user_prompt]
        for page in source_pages:
            parts.append(types.Part.from_bytes(data=page, mime_type="image/png"))

        resp = client.models.generate_content(
            model=self.model,
            contents=parts,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                max_output_tokens=self.max_tokens,
            ),
        )
        text = resp.text or ""
        meta = getattr(resp, "usage_metadata", None)
        return (
            text,
            getattr(meta, "prompt_token_count", 0) or 0,
            getattr(meta, "candidates_token_count", 0) or 0,
        )


def _strip_json_fences(raw_text: str) -> str:
    """Strip stray ```json``` markdown fences from a model response."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.lstrip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.rstrip("`").strip()
    return text


def parse_judge_flags(raw_text: str) -> list[ValidationFlag]:
    """Parse ``{"flags": [...]}`` JSON into typed :class:`ValidationFlag`\\ s.

    Tolerant of stray markdown fences. Returns an empty list when the response
    is unparseable so the caller can decide whether to retry.

    Reads both the ``score`` (Likert 1-5) and ``severity`` fields. ``score``
    defaults to 0 when the judge omits it (severity-mode behaviour).
    """
    text = _strip_json_fences(raw_text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Could not decode judge response as JSON; first 200 chars: %s", text[:200])
        return []

    flags = data.get("flags") if isinstance(data, dict) else data
    if not isinstance(flags, list):
        return []

    parsed: list[ValidationFlag] = []
    for entry in flags:
        if not isinstance(entry, dict):
            continue
        try:
            severity_raw = str(entry.get("severity", "")).lower()
            if severity_raw not in ("ok", "suspect", "wrong"):
                continue
            severity: Severity = severity_raw  # type: ignore[assignment]
            parsed.append(
                ValidationFlag(
                    item_index=int(entry.get("item_index", -1)),
                    field=str(entry.get("field", "")),
                    severity=severity,
                    score=_clamp_score(entry.get("score", 0)),
                    reason=str(entry.get("reason", "")),
                    suggested_value=(
                        str(entry["suggested_value"])
                        if entry.get("suggested_value") is not None
                        else None
                    ),
                )
            )
        except (TypeError, ValueError):
            continue
    return parsed


def _clamp_score(raw: Any) -> int:
    """Coerce a raw score to a 0..5 integer (0 = unspecified)."""
    try:
        score = int(round(float(raw)))
    except (TypeError, ValueError):
        return 0
    if score < 0:
        return 0
    if score > 5:
        return 5
    return score
