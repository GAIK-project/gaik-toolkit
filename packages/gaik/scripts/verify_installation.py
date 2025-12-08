#!/usr/bin/env python3
"""Smoke test that gaik installs and exposes its public API."""

from __future__ import annotations

from gaik import __version__


def run_checks() -> None:
    print(f"gaik version detected: {__version__}")

    # Test optional extractor module if available
    try:
        from gaik.extractor import SchemaGenerator, DataExtractor, get_openai_config

        print("[OK] extractor module verification passed")
    except ImportError as e:
        print(f"[SKIP] extractor module skipped (optional dependencies not installed): {e}")

    # Test optional parser module if available
    try:
        from gaik.parsers import VisionParser, PyMuPDFParser, DoclingParser

        print("[OK] parser module verification passed")
    except ImportError as e:
        print(f"[SKIP] parser module skipped (optional dependencies not installed): {e}")

    # Test optional transcriber module if available
    try:
        from gaik.transcriber import Transcriber, get_openai_config

        print("[OK] transcriber module verification passed")
    except ImportError as e:
        print(f"[SKIP] transcriber module skipped (optional dependencies not installed): {e}")

    print("[OK] Core gaik installation verified")


if __name__ == "__main__":
    run_checks()
