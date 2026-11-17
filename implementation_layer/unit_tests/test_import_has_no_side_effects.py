"""Importing gaik reads no .env file and leaves the host's logging alone (G47)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap

MODULES = [
    "gaik.software_components.config",
    "gaik.software_components.llm.config",
    "gaik.software_components.parsers.docx_parser",
    "gaik.software_components.parsers.pymypdf",
    "gaik.software_components.parsers.vision",
    "gaik.software_components.parsers.multimodal_parser.config",
    "gaik.software_components.doc_classifier.classifier",
    "gaik.software_components.parallel_transcriber.config",
    "gaik.software_components.text_to_speech.text_to_speech",
    "gaik.software_components.endpoints",
]


def _run(code: str, **env: str) -> dict:
    """Run ``code`` in a fresh interpreter that records dotenv loads; return its JSON."""
    prelude = textwrap.dedent(
        """
        import importlib, json, logging, os, sys
        import dotenv
        loads = []
        def record(*args, **kwargs):
            loads.append(1)
            os.environ["GAIK_TEST_FROM_DOTENV"] = "yes"
            return True
        dotenv.load_dotenv = record
        dotenv.main.load_dotenv = record
        before = (logging.getLogger().level, list(logging.getLogger().handlers))
        """
    )
    environment = {k: v for k, v in os.environ.items() if k != "GAIK_NO_DOTENV"}
    environment.update(env)
    out = subprocess.run(
        [sys.executable, "-c", prelude + textwrap.dedent(code)],
        capture_output=True,
        text=True,
        env=environment,
        check=True,
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_importing_the_components_loads_no_dotenv_and_keeps_logging():
    result = _run(
        f"""
        imported = []
        for name in {MODULES!r}:
            try:
                importlib.import_module(name)
                imported.append(name)
            except ImportError:
                pass
        root = logging.getLogger()
        print(json.dumps({{
            "imported": imported,
            "loads": len(loads),
            "logging_kept": (root.level, list(root.handlers)) == before,
        }}))
        """
    )

    assert len(result["imported"]) >= 3
    assert result["loads"] == 0
    assert result["logging_kept"] is True


def test_the_first_config_read_loads_dotenv_once():
    result = _run(
        """
        from gaik.software_components.llm.config import get_llm_config
        from gaik.software_components.config import get_openai_config
        for _ in range(3):
            try:
                get_llm_config("openai")
            except Exception:
                pass
            get_openai_config(use_azure=True)
        print(json.dumps({"loads": len(loads)}))
        """
    )

    assert result["loads"] == 1


def test_gaik_no_dotenv_skips_the_file():
    result = _run(
        """
        from gaik.software_components.config import get_openai_config
        get_openai_config(use_azure=True)
        print(json.dumps({"loads": len(loads)}))
        """,
        GAIK_NO_DOTENV="1",
    )

    assert result["loads"] == 0
