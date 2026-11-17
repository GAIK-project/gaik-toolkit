"""EU AI Act screening router.

The demo's screening agent (a Next.js route) writes the screening as data; this endpoint runs
the agent skill's own checker (`scripts/check_screening.py` of the `ai-act-use-case-screening`
skill) over it. The checker is the skill's rule set: evidence quoted exactly from the user's
words, citations only from the reference's list, a class that follows from the findings.

The endpoint is stateless. Each call writes the intake, the screening and the report to a
temporary folder, runs the checker and deletes the folder. It calls no model.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

logger = logging.getLogger("demo_api.ai_act_screening")

router = APIRouter()

SKILL_NAME = "ai-act-use-case-screening"
SKILL_RELATIVE = Path("implementation_layer/no-code-assets/agent-skills/skills") / SKILL_NAME
MAX_JSON_BYTES = 400_000
MAX_REPORT_CHARS = 60_000


def _skill_dir() -> Path:
    """The skill folder: AI_ACT_SKILL_DIR, else the repository path above this file."""
    configured = os.environ.get("AI_ACT_SKILL_DIR")
    if configured and (Path(configured) / "scripts" / "check_screening.py").is_file():
        return Path(configured)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / SKILL_RELATIVE
        if (candidate / "scripts" / "check_screening.py").is_file():
            return candidate
    raise FileNotFoundError("the AI Act screening skill folder was not found")


@lru_cache(maxsize=1)
def _checker() -> ModuleType:
    path = _skill_dir() / "scripts" / "check_screening.py"
    spec = importlib.util.spec_from_file_location("ai_act_check_screening", path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load the screening checker")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CheckRequest(BaseModel):
    intake: dict[str, Any]
    screening: dict[str, Any]
    report: str = Field(default="", max_length=MAX_REPORT_CHARS)


class CheckResponse(BaseModel):
    ok: bool
    errors: list[str]
    warnings: list[str]
    screening: dict[str, Any] | None = None


def run_check(intake: dict[str, Any], screening: dict[str, Any], report: str) -> CheckResponse:
    """Check one screening. The server stamps the two values the model cannot know."""
    checker = _checker()
    with tempfile.TemporaryDirectory(prefix="ai-act-screening-") as tmp:
        folder = Path(tmp)
        (folder / "intake.json").write_text(
            json.dumps(intake, ensure_ascii=False), encoding="utf-8"
        )
        try:
            digest = checker.intake_hash(folder)
        except (OSError, ValueError, TypeError, AttributeError):
            digest = ""
        stamped = dict(screening)
        stamped["screening_version"] = "1.0"
        if digest:
            stamped["intake_sha256"] = digest
        try:
            _, verified = checker.load_reference(checker.REFERENCE.read_text(encoding="utf-8"))
        except OSError:
            verified = None
        if verified:
            stamped["reference_last_verified"] = verified
        (folder / "screening.json").write_text(
            json.dumps(stamped, ensure_ascii=False), encoding="utf-8"
        )
        if report.strip():
            (folder / "report.md").write_text(report, encoding="utf-8")
        rep = checker.check(folder)
    ok = not rep.errors
    return CheckResponse(
        ok=ok,
        errors=rep.errors[:40],
        warnings=rep.warnings[:40],
        screening=stamped if ok else None,
    )


@router.post("/check", response_model=CheckResponse)
async def check_screening(request: CheckRequest) -> CheckResponse:
    """Run the skill's checker over an intake and a screening."""
    size = len(json.dumps(request.intake)) + len(json.dumps(request.screening))
    if size > MAX_JSON_BYTES:
        raise HTTPException(status_code=413, detail="The screening is too large to check.")
    try:
        return await run_in_threadpool(run_check, request.intake, request.screening, request.report)
    except FileNotFoundError:
        logger.error("AI Act screening skill folder missing")
        raise HTTPException(
            status_code=503, detail="The screening checker is not available on this server."
        ) from None
