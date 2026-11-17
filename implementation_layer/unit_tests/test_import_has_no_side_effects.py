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

    # the modules that used to configure logging must really have been imported
    for name in (
        "gaik.software_components.parsers.docx_parser",
        "gaik.software_components.parsers.pymypdf",
        "gaik.software_components.doc_classifier.classifier",
        "gaik.software_components.llm.config",
    ):
        assert name in result["imported"]
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
        print(json.dumps({
            "loads": len(loads), "value": os.environ.get("GAIK_TEST_FROM_DOTENV")
        }))
        """
    )

    assert result["loads"] == 1
    assert result["value"] == "yes"  # what the file set is there for the config


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


def test_a_second_thread_waits_until_the_file_is_read():
    result = _run(
        """
        import threading, time
        def slow(*args, **kwargs):
            time.sleep(0.3)
            os.environ["GAIK_TEST_FROM_DOTENV"] = "yes"
            loads.append(1)
            return True
        dotenv.load_dotenv = slow
        from gaik.software_components.env_file import load_env_file
        seen = []
        def read():
            load_env_file()
            seen.append(os.environ.get("GAIK_TEST_FROM_DOTENV"))
        threads = [threading.Thread(target=read) for _ in range(4)]
        for t in threads: t.start()
        for t in threads: t.join()
        print(json.dumps({"loads": len(loads), "seen": seen}))
        """
    )

    assert result["loads"] == 1
    assert result["seen"] == ["yes"] * 4


def test_the_report_skill_reads_llm_provider_from_dotenv():
    from pathlib import Path

    script = (
        Path(__file__).parents[1]
        / "no-code-assets/agent-skills/skills/generate-structured-reports/scripts/run_report.py"
    )
    result = _run(
        f"""
        def from_file(*args, **kwargs):
            os.environ["LLM_PROVIDER"] = "anthropic"
            loads.append(1)
            return True
        dotenv.load_dotenv = from_file
        os.environ.pop("LLM_PROVIDER", None)
        import importlib.util
        spec = importlib.util.spec_from_file_location("run_report", {str(script)!r})
        module = importlib.util.module_from_spec(spec)
        sys.modules["run_report"] = module
        spec.loader.exec_module(module)
        print(json.dumps({{"provider": module.provider_name(None)}}))
        """
    )

    assert result["provider"] == "anthropic"
