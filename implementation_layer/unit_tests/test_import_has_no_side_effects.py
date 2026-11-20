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
        def from_file(*args, **kwargs):
            loads.append(1)
            os.environ["OPENAI_API_KEY"] = "key-from-dotenv"
            return True
        dotenv.load_dotenv = from_file
        os.environ.pop("OPENAI_API_KEY", None)
        from gaik.software_components.llm.config import get_llm_config
        from gaik.software_components.config import get_openai_config
        keys = []
        for _ in range(3):
            keys.append(get_llm_config("openai")["api_key"])
            get_openai_config(use_azure=True)
        print(json.dumps({"loads": len(loads), "keys": keys}))
        """
    )

    assert result["loads"] == 1
    # the first read already returns what the file set
    assert result["keys"] == ["key-from-dotenv"] * 3


def test_a_failed_dotenv_read_is_tried_again():
    result = _run(
        """
        def flaky(*args, **kwargs):
            loads.append(1)
            if len(loads) == 1:
                raise OSError("busy")
            os.environ["OPENAI_API_KEY"] = "key-from-dotenv"
            return True
        dotenv.load_dotenv = flaky
        os.environ.pop("OPENAI_API_KEY", None)
        from gaik.software_components.llm.config import get_llm_config
        try:
            get_llm_config("openai")
            first = "returned"
        except OSError:
            first = "raised"
        key = get_llm_config("openai")["api_key"]
        print(json.dumps({"loads": len(loads), "first": first, "key": key}))
        """
    )

    assert result["first"] == "raised"
    assert result["loads"] == 2
    assert result["key"] == "key-from-dotenv"


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


def test_the_scraper_and_the_jev_classifier_read_no_dotenv():
    # Neither read a .env before; a planted file must not set their proxy or endpoint.
    result = _run(
        """
        try:
            from gaik.software_components.web_scraper.connect import environment_proxy_mounts
            environment_proxy_mounts()
        except ImportError:
            pass
        # No base_url, so the classifier reads TYPESAFE_BASE_URL; the endpoint check
        # runs before the SDK import, so the read happens without the extra too.
        os.environ.pop("TYPESAFE_BASE_URL", None)
        try:
            from gaik.software_components.jev_classifier import JevClassifier
            JevClassifier(api_key="k", base_url=None)
        except ImportError:
            pass
        print(json.dumps({"loads": len(loads)}))
        """
    )

    assert result["loads"] == 0


def test_the_unit_test_setup_loads_the_repository_dotenv():
    # The live tests read their keys at import, so the setup loads the file first.
    from pathlib import Path

    conftest = Path(__file__).with_name("conftest.py")
    result = _run(
        f"""
        import importlib.util
        spec = importlib.util.spec_from_file_location("unit_test_setup", {str(conftest)!r})
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        print(json.dumps({{
            "loads": len(loads), "value": os.environ.get("GAIK_TEST_FROM_DOTENV")
        }}))
        """
    )

    assert result["loads"] == 1
    assert result["value"] == "yes"


# A legacy client config with a key and no base_url: the endpoint check and the SDK
# then read OPENAI_BASE_URL, so a value kept only in .env must be loaded before that.
_BASE_URL_FROM_FILE = """
        def from_file(*args, **kwargs):
            loads.append(1)
            os.environ["OPENAI_BASE_URL"] = "https://llm.example.test/v1"
            return True
        dotenv.load_dotenv = from_file
        os.environ.pop("OPENAI_BASE_URL", None)
        os.environ.pop("GAIK_ALLOWED_ENDPOINT_HOSTS", None)
        """


def test_a_legacy_vision_parser_client_uses_the_base_url_from_dotenv():
    result = _run(
        _BASE_URL_FROM_FILE
        + """
        from gaik.software_components.parsers.vision import VisionParser
        parser = VisionParser({"use_azure": False, "api_key": "k", "model": "m"})
        print(json.dumps({"loads": len(loads), "base_url": str(parser._client.base_url)}))
        """
    )

    assert result["loads"] == 1
    assert result["base_url"].startswith("https://llm.example.test/v1")


def test_a_legacy_multimodal_client_uses_the_base_url_from_dotenv():
    # VisionExtractor builds its OpenAI client with this helper.
    result = _run(
        _BASE_URL_FROM_FILE
        + """
        from gaik.software_components.parsers.multimodal_parser import config
        from gaik.software_components.vision_extractor import vision_extractor
        assert vision_extractor.create_openai_client is config.create_openai_client
        client = config.create_openai_client({"use_azure": False, "api_key": "k"})
        print(json.dumps({"loads": len(loads), "base_url": str(client.base_url)}))
        """
    )

    assert result["loads"] == 1
    assert result["base_url"].startswith("https://llm.example.test/v1")


def test_a_legacy_shared_config_client_uses_the_base_url_from_dotenv():
    # Here resolve_provider loads the file before the endpoint is read.
    result = _run(
        _BASE_URL_FROM_FILE
        + """
        from gaik.software_components.config import create_openai_client
        client = create_openai_client({"use_azure": False, "api_key": "k"})
        print(json.dumps({"loads": len(loads), "base_url": str(client.base_url)}))
        """
    )

    assert result["loads"] == 1
    assert result["base_url"].startswith("https://llm.example.test/v1")


def test_the_provider_examples_find_keys_kept_in_the_gaik_dotenv(tmp_path):
    # Keys only in the file gaik loads (the repository .env), none in the examples'
    # folder: the examples still list the provider.
    from pathlib import Path

    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=key-from-root-dotenv\n", encoding="utf-8")
    folder = Path(__file__).parents[1] / "examples/software_components/llm"
    scripts = [
        str(folder / "example_multi_provider_extractor.py"),
        str(folder / "example_provider_client_basics.py"),
    ]
    result = _run(
        f"""
        for name in ("AZURE_API_KEY", "AZURE_ENDPOINT", "OPENAI_API_KEY",
                     "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"):
            os.environ.pop(name, None)
        def gaik_file(*args, **kwargs):
            # gaik's loader calls load_dotenv() without a path; an example's own call
            # names its folder's file, which holds nothing here.
            if args or kwargs.get("dotenv_path"):
                return False
            loads.append(1)
            for key, value in dotenv.dotenv_values({str(env_file)!r}).items():
                os.environ.setdefault(key, value)
            return True
        dotenv.load_dotenv = gaik_file
        import importlib.util
        found = []
        for index, script in enumerate({scripts!r}):
            spec = importlib.util.spec_from_file_location(f"provider_example_{{index}}", script)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            found.append(module.available_providers())
        print(json.dumps({{"found": found}}))
        """
    )

    assert result["found"] == [["anthropic"], ["anthropic"]]
