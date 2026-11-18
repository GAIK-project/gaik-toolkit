"""Docling's Tesseract OCR options, limited to the languages the install has.

Docling's Tesseract options default to English, Spanish, French and German, and
Docling 2.132 and later refuses to start Tesseract OCR while one of them has no
traineddata. Docling 2.64 handed Tesseract all four and Tesseract skipped the
missing ones, so an install with English alone (the Debian and Ubuntu
``tesseract-ocr`` package, the Windows installer's default) worked.

:func:`with_installed_languages` keeps that: it passes Docling the default
languages that are installed. When none is, or the languages cannot be listed,
it leaves Docling's default in place, so Docling's own error explains the install.
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Iterable
from typing import Any

logger = logging.getLogger(__name__)

_LIST_TIMEOUT_S = 30


def installed_tesseract_cli_languages(tesseract_cmd: str = "tesseract") -> set[str] | None:
    """Languages ``tesseract --list-langs`` reports, or ``None`` if it cannot be run."""
    try:
        proc = subprocess.run(
            [tesseract_cmd, "--list-langs"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_LIST_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    # Tesseract prints a "List of available languages ..." header, then one per line.
    lines = f"{proc.stdout}\n{proc.stderr}".splitlines()
    return {
        line.strip()
        for line in lines
        if line.strip() and not line.startswith("List of available languages")
    }


def installed_tesserocr_languages() -> set[str] | None:
    """Languages the tesserocr bindings report, or ``None`` if tesserocr is missing."""
    try:
        import tesserocr  # type: ignore[import-not-found]

        _, languages = tesserocr.get_languages()
    except Exception:
        return None
    return set(languages)


def with_installed_languages(
    options_cls: Any, installed: Iterable[str] | None, **kwargs: Any
) -> Any:
    """``options_cls(**kwargs)`` with its default languages cut down to ``installed``.

    ``options_cls`` is Docling's ``TesseractCliOcrOptions`` or ``TesseractOcrOptions``.
    The default list keeps its order, which Tesseract reads as preference.
    """
    default = list(options_cls.model_fields["lang"].default)
    available = set(installed or ())
    kept = [lang for lang in default if lang in available]
    if not kept or kept == default:
        return options_cls(**kwargs)
    logger.warning(
        "Tesseract has no traineddata for %s, so OCR leaves out those default languages and "
        "uses %s; install them to read documents in those languages",
        ", ".join(lang for lang in default if lang not in available),
        ", ".join(kept),
    )
    return options_cls(lang=kept, **kwargs)
