"""LLM-as-Judge router — text-pair, hallucination, validate, panel."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

try:
    from utils import validate_file_size
except ImportError:
    from api.utils import validate_file_size

import fitz
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

JudgeProvider = Literal["openai", "azure", "anthropic", "google"]
ScoringMode = Literal["severity", "likert_1_5", "additive"]

# Default panel: three models giving a cost/speed disagreement signal. The
# provider on each spec is auto-resolved at call time (see _resolve_provider)
# to whatever credentials the deployment has — Azure on Rahti, OpenAI on the
# 8Wave fork — so the same model names work on either. The frontend may send
# its own panel specs to override this.
DEFAULT_PANEL_JUDGES: tuple[dict[str, str], ...] = (
    {"provider": "openai", "model": "gpt-5.4-mini"},
    {"provider": "openai", "model": "gpt-5.4"},
    {"provider": "openai", "model": "gpt-5.1"},
)
JUDGE_NOT_AVAILABLE_DETAIL = (
    "LLMJudge requires gaik>=0.4.0. "
    "Provider extras (gaik[llm-anthropic] / gaik[llm-google]) are needed "
    "for the matching providers."
)

# Which env var(s) signal that a provider is configured on this deployment.
_PROVIDER_ENV_KEYS: dict[str, tuple[str, ...]] = {
    "azure": ("AZURE_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "google": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
}
# Fallback preference order when the requested provider has no credentials.
_PROVIDER_PREFERENCE: tuple[str, ...] = ("azure", "openai", "anthropic", "google")


def _provider_configured(provider: str) -> bool:
    return any(os.getenv(k) for k in _PROVIDER_ENV_KEYS.get(provider, ()))


def _resolve_provider(requested: JudgeProvider) -> JudgeProvider:
    """Return the requested provider if its credentials are present, otherwise
    fall back to the first configured provider. Lets the demo run on an
    OpenAI-only deployment (the 8Wave fork) as well as an Azure one without the
    caller needing to know which keys exist."""
    if _provider_configured(requested):
        return requested
    for candidate in _PROVIDER_PREFERENCE:
        if _provider_configured(candidate):
            return candidate  # type: ignore[return-value]
    return requested  # nothing configured — let LLMJudge raise a clear error


def _make_judge(provider: JudgeProvider, model: str | None):
    """Construct an LLMJudge with friendly errors for missing deps / creds."""
    try:
        from gaik.software_components.validators import LLMJudge
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"{JUDGE_NOT_AVAILABLE_DETAIL} ({e})") from e

    provider = _resolve_provider(provider)
    # LLMJudge defaults use_azure=True, which would force the Azure OpenAI config
    # even for the plain "openai" provider. Drive it from the environment so an
    # OpenAI-only deployment uses standard OpenAI.
    use_azure = bool(os.getenv("AZURE_API_KEY"))
    try:
        return LLMJudge(model_provider=provider, model=model or None, use_azure=use_azure)
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Provider SDK for '{provider}' is not installed. "
                f"Try `pip install 'gaik[llm-{provider}]'`. ({e})"
            ),
        ) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _flag_dict(flag) -> dict[str, Any]:
    return asdict(flag)


def _usage_dict(usage) -> dict[str, Any] | None:
    return asdict(usage) if usage is not None else None


def _render_pdf_pages(pdf_bytes: bytes, dpi: int = 150, max_pages: int = 5) -> list[bytes]:
    """Render PDF bytes into PNG byte streams (one per page, capped)."""
    pages: list[bytes] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        page_count = min(len(doc), max_pages)
        if len(doc) > max_pages:
            logger.info(
                "PDF has %s pages; capping judge input at %s pages.",
                len(doc),
                max_pages,
            )
        for i in range(page_count):
            pix = doc[i].get_pixmap(dpi=dpi)
            pages.append(pix.tobytes("png"))
    return pages


# ─────────────────── Text-pair ───────────────────


class TextPairRequest(BaseModel):
    extracted_text: str
    expected_text: str
    field_name: str | None = None
    context: str | None = None
    provider: JudgeProvider = "azure"
    model: str | None = None


@router.post("/text-pair")
async def text_pair(request: TextPairRequest):
    """Judge whether two short texts mean the same thing (no source document)."""
    if not request.extracted_text and not request.expected_text:
        raise HTTPException(status_code=400, detail="Both inputs are empty")

    judge = _make_judge(request.provider, request.model)
    try:
        verdict = judge.judge_text_pair(
            extracted_text=request.extracted_text,
            expected_text=request.expected_text,
            field_name=request.field_name,
            context=request.context,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Judge call failed: {e}") from e

    return {
        "equivalent": verdict.equivalent,
        "severity": verdict.severity,
        "score": verdict.score,
        "reason": verdict.reason,
        "usage": _usage_dict(verdict.usage),
    }


# ─────────────────── Hallucination detection ───────────────────


class HallucinationRequest(BaseModel):
    source_text: str
    extracted: dict
    field_descriptions: dict[str, str] | None = None
    provider: JudgeProvider = "azure"
    model: str | None = None


@router.post("/hallucinations")
async def hallucinations(request: HallucinationRequest):
    """Identify fields in `extracted` whose values are not supported by `source_text`."""
    if not request.source_text:
        raise HTTPException(status_code=400, detail="source_text is required")
    if not isinstance(request.extracted, dict) or not request.extracted:
        raise HTTPException(status_code=400, detail="extracted must be a non-empty JSON object")

    judge = _make_judge(request.provider, request.model)
    try:
        report = judge.detect_hallucinations(
            source_text=request.source_text,
            extracted=request.extracted,
            field_descriptions=request.field_descriptions,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Judge call failed: {e}") from e

    return {
        "flags": [_flag_dict(f) for f in report.flags],
        "raw_judge_text": report.raw_judge_text,
        "usage": _usage_dict(report.usage),
    }


# ─────────────────── PDF validation ───────────────────


@router.post("/validate")
async def validate_pdf(
    pdf: UploadFile = File(..., description="Source PDF the judge will inspect"),
    extracted: str = Form(..., description="Extracted JSON (dict or list of dicts)"),
    rubric: str | None = Form(None, description="Optional ValidationRubric as JSON"),
    provider: JudgeProvider = Form("azure"),
    model: str | None = Form(None),
    scoring_mode: ScoringMode = Form("likert_1_5"),
):
    """Validate an extractor's JSON output against PDF page images using LLMJudge."""
    if not pdf.filename or not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf is supported")

    try:
        extracted_payload = json.loads(extracted)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid extracted JSON: {e}") from e

    if rubric:
        try:
            rubric_payload = json.loads(rubric)
            if not isinstance(rubric_payload, dict):
                raise ValueError("rubric must decode to an object")
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(status_code=400, detail=f"Invalid rubric JSON: {e}") from e
    else:
        rubric_payload = {}

    rubric_payload.setdefault("scoring_mode", scoring_mode)

    content = await validate_file_size(pdf)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            pages = _render_pdf_pages(content)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to render PDF: {e}") from e

        if not pages:
            raise HTTPException(status_code=400, detail="PDF has no pages to inspect")

        try:
            from gaik.software_components.validators import ValidationRubric
        except ImportError as e:
            raise HTTPException(status_code=503, detail=f"{JUDGE_NOT_AVAILABLE_DETAIL} ({e})") from e

        try:
            rubric_obj = ValidationRubric(**rubric_payload)
        except TypeError as e:
            raise HTTPException(status_code=400, detail=f"Unknown rubric field: {e}") from e

        judge = _make_judge(provider, model)
        try:
            result = judge.validate(pages, extracted_payload, rubric_obj)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Judge call failed: {e}") from e

        return {
            "flags": [_flag_dict(f) for f in result.flags],
            "raw_judge_text": result.raw_judge_text,
            "usage": _usage_dict(result.usage),
            "pages_rendered": len(pages),
        }
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


# ─────────────────── Panel (text-pair) ───────────────────


class PanelJudgeSpec(BaseModel):
    provider: JudgeProvider
    model: str | None = None


class PanelTextPairRequest(BaseModel):
    extracted_text: str
    expected_text: str
    field_name: str | None = None
    context: str | None = None
    # Backwards-compatible: clients may still pass a flat provider list.
    providers: list[JudgeProvider] | None = None
    # Preferred: explicit (provider, model) pairs — lets the UI run multiple
    # Azure models when cross-provider credentials aren't configured.
    judges: list[PanelJudgeSpec] | None = None


@router.post("/panel/text-pair")
async def panel_text_pair(request: PanelTextPairRequest):
    """Run the text-pair judgement across multiple judges and report agreement."""
    if request.judges:
        specs: list[PanelJudgeSpec] = list(request.judges)
    elif request.providers:
        specs = [PanelJudgeSpec(provider=p) for p in request.providers]
    else:
        specs = [PanelJudgeSpec(**spec) for spec in DEFAULT_PANEL_JUDGES]

    if len(specs) < 2:
        raise HTTPException(status_code=400, detail="Panel needs at least 2 judges")
    if not request.extracted_text and not request.expected_text:
        raise HTTPException(status_code=400, detail="Both inputs are empty")

    built_judges: list[tuple[str, Any]] = []  # (label, judge)
    skipped: list[dict[str, str]] = []

    for spec in specs:
        label = f"{spec.provider}/{spec.model}" if spec.model else spec.provider
        try:
            judge = _make_judge(spec.provider, spec.model)
        except HTTPException as e:
            if e.status_code == 503:
                skipped.append({"provider": label, "reason": str(e.detail)})
                continue
            raise
        built_judges.append((label, judge))

    if len(built_judges) < 2:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Not enough judges available for a panel",
                "skipped": skipped,
            },
        )

    per_judge: list[dict[str, Any]] = []
    severities: list[str] = []
    total_cost = 0.0
    total_duration = 0.0

    for label, judge in built_judges:
        try:
            verdict = judge.judge_text_pair(
                extracted_text=request.extracted_text,
                expected_text=request.expected_text,
                field_name=request.field_name,
                context=request.context,
            )
        except Exception as e:
            per_judge.append({"provider": label, "error": str(e)})
            continue

        severities.append(verdict.severity)
        usage = _usage_dict(verdict.usage)
        if usage:
            total_cost += usage.get("cost_usd") or 0.0
            total_duration += usage.get("duration_s") or 0.0
        per_judge.append(
            {
                "provider": label,
                "equivalent": verdict.equivalent,
                "severity": verdict.severity,
                "score": verdict.score,
                "reason": verdict.reason,
                "usage": usage,
            }
        )

    successful = [v for v in per_judge if "error" not in v]
    if not successful:
        raise HTTPException(
            status_code=502,
            detail={"message": "All panel judges failed", "per_judge": per_judge},
        )

    agreement = (
        sum(1 for s in severities if s == severities[0]) / len(severities) if severities else 0.0
    )

    return {
        "per_judge": per_judge,
        "skipped": skipped,
        "agreement_score": agreement,
        "total_cost_usd": total_cost,
        "total_duration_s": total_duration,
    }
