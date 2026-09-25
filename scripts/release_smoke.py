"""Bounded, authenticated component smoke test used by release_check.py.

All prompts and documents are synthetic. No response bodies, credentials, or
exception messages are written to the result. This is a real provider test,
not a credential-presence check; every required component must return a
semantically correct result for the selected model.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import math
import os
import subprocess
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

REQUIRED_CHECKS = (
    "chat",
    "stream",
    "schema_generator",
    "data_extractor",
    "answer_generator",
    "document_classifier",
)

LITELLM_PREFIXES = {
    "azure": "azure/",
    "openai": "openai/",
    "aitta": "openai/",
    "google": "gemini/",
    "anthropic": "anthropic/",
}


def backend_config(config: dict, provider: str, backend: str) -> dict:
    if backend == "native":
        return config
    if provider not in LITELLM_PREFIXES:
        raise ValueError("This provider has no certified LiteLLM release mapping")
    result = dict(config)
    result["provider"] = "litellm"
    result["model"] = LITELLM_PREFIXES[provider] + config["model"]
    if provider == "azure":
        result["base_url"] = config["azure_endpoint"]
    return result


class CallBudget:
    """Shared call/output allowance across the actual component-created clients."""

    def __init__(self, max_calls: int, output_tokens: int):
        self.max_calls = max_calls
        self.output_tokens = output_tokens
        self.calls = 0

    def options(self, provider, kwargs, *, embedding=False):
        if self.calls >= self.max_calls:
            raise RuntimeError("Live release request budget exceeded")
        self.calls += 1
        options = dict(kwargs)
        if not embedding:
            key = "max_completion_tokens" if provider in {"openai", "azure"} else "max_tokens"
            options[key] = self.output_tokens
        return options


class BoundedClient:
    """Preserve an actual ProviderClient while adding a shared budget."""

    def __init__(self, client, *, max_calls=10, output_tokens=2048, budget=None):
        self._client = client
        self.provider = client.provider
        self.model = client.model
        self.raw = client.raw
        self.budget = budget or CallBudget(max_calls, output_tokens)

    @property
    def calls(self):
        return self.budget.calls

    def _options(self, kwargs):
        return self.budget.options(self.provider, kwargs)

    def chat(self, messages, **kwargs):
        return self._client.chat(messages, **self._options(kwargs))

    def chat_stream(self, messages, **kwargs):
        return self._client.chat_stream(messages, **self._options(kwargs))

    def chat_parsed(self, messages, response_format, **kwargs):
        return self._client.chat_parsed(messages, response_format, **self._options(kwargs))

    def embed(self, texts, **kwargs):
        return self._client.embed(
            texts, **self.budget.options(self.provider, kwargs, embedding=True)
        )


class BoundedOpenAIClient:
    """Preserve the raw SDK call path, including component-generated kwargs.

    This deliberately does not implement ProviderClient. Switching a component
    to that protocol would hide regressions in its legacy OpenAI/Azure branch.
    Each resource method forwards to the original constructed SDK instance.
    """

    def __init__(self, raw, provider, budget):
        self.raw = raw

        def capped(method, *, embedding=False):
            def call(**kwargs):
                return method(**budget.options(provider, kwargs, embedding=embedding))

            return call

        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=capped(raw.chat.completions.create))
        )
        self.beta = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(parse=capped(raw.beta.chat.completions.parse))
            )
        )
        self.embeddings = SimpleNamespace(create=capped(raw.embeddings.create, embedding=True))


def _close(client):
    raw = getattr(client, "raw", client)
    close = getattr(raw, "close", None)
    if callable(close):
        close()


def _budget_component(component, client, created_clients, provider):
    from gaik.software_components.llm.base import ProviderClient

    original = component.client
    created_clients.append(original)
    if isinstance(original, ProviderClient):
        component.client = BoundedClient(original, budget=client.budget)
    else:
        component.client = BoundedOpenAIClient(original, provider, client.budget)
    return component


def run_smoke(args) -> dict:
    from gaik.software_components.llm import create_llm_client, get_llm_config

    config = get_llm_config(
        args.provider,
        model=args.model,
        timeout=args.timeout,
        max_retries=0,
    )
    if args.provider == "aitta":
        if str(config["base_url"]).rstrip("/") != "https://aitta-api.csc.fi/openai/v1":
            raise ValueError("Aitta release checks require CSC's documented endpoint")
    config = backend_config(config, args.provider, args.backend)
    client = BoundedClient(
        create_llm_client(config), max_calls=args.max_calls, output_tokens=args.output_tokens
    )
    created_clients = [client]

    def bounded(component):
        return _budget_component(component, client, created_clients, args.provider)

    result = {
        "provider": args.provider,
        "model": args.model,
        "backend": args.backend,
        "routed_model": config["model"],
        "checks": {},
        "authenticated_live": False,
        "ok": False,
    }

    def check(name, operation):
        started = time.monotonic()
        try:
            operation()
        except Exception as exc:
            result["checks"][name] = {
                "ok": False,
                "error_type": type(exc).__name__,
                "status_code": getattr(exc, "status_code", None),
                "elapsed_s": round(time.monotonic() - started, 2),
            }
            raise
        result["checks"][name] = {
            "ok": True,
            "elapsed_s": round(time.monotonic() - started, 2),
        }

    def chat():
        response = client.chat([{"role": "user", "content": "Reply with exactly: GAIK_OK"}])
        if "GAIK_OK" not in response.text:
            raise AssertionError("Chat did not return the requested marker")
        result["authenticated_live"] = True

    def stream():
        text = "".join(
            client.chat_stream([{"role": "user", "content": "Reply with exactly: GAIK_OK"}])
        )
        if "GAIK_OK" not in text:
            raise AssertionError("Streaming did not return the requested marker")

    try:
        check("chat", chat)
        check("stream", stream)

        from gaik.software_components.extractor import DataExtractor, SchemaGenerator

        requirement = (
            "Extract one flat record per document with exactly these two required string fields: "
            "1. project: the project name exactly as written. "
            "2. city: the city name exactly as written. "
            "The JSON property names MUST be exactly project and city, lowercase, with no "
            "prefixes, suffixes, wrapper objects, or additional fields. "
            'Example output shape: {"project": "GAIK", "city": "Helsinki"}. '
            "The example values are illustrative, not defaults. Copy values from the document."
        )
        generator = bounded(SchemaGenerator(config))
        generated = {}

        def schema_generator():
            generated["model"] = generator.generate_schema(requirement)
            result["schema_observation"] = {
                "field_names": list(generated["model"].model_fields),
                "structure_type": generator.structure_analysis.structure_type,
            }
            if set(generated["model"].model_fields) != {"project", "city"}:
                raise AssertionError("SchemaGenerator did not generate the requested fields")

        check("schema_generator", schema_generator)

        def data_extractor():
            extractor = bounded(DataExtractor(config))
            records = extractor.extract(
                extraction_model=generated["model"],
                requirements=generator.item_requirements,
                user_requirements=requirement,
                documents=["Project: GAIK. City: Helsinki."],
            )
            if records != [{"project": "GAIK", "city": "Helsinki"}]:
                raise AssertionError("DataExtractor did not preserve the synthetic record")

        check("data_extractor", data_extractor)

        def answer_generator():
            from gaik.software_components.RAG.answer_generator import AnswerGenerator

            generator = bounded(AnswerGenerator(config=config, stream=False))
            answer = generator.generate("Which city hosts project GAIK?", "GAIK is in Helsinki.")
            if "helsinki" not in str(answer).lower():
                raise AssertionError("AnswerGenerator did not answer from the supplied context")

        check("answer_generator", answer_generator)

        def document_classifier():
            import fitz
            from gaik.software_components.doc_classifier import DocumentClassifier

            with tempfile.TemporaryDirectory(prefix="gaik-release-fixture-") as temp:
                path = Path(temp) / "release-fixture.pdf"
                with fitz.open() as document:
                    page = document.new_page()
                    page.insert_text((72, 72), "INVOICE\nInvoice number: GAIK-001\nTotal: EUR 12")
                    document.save(path)
                classifier = bounded(DocumentClassifier(config))
                classified = classifier.classify(str(path), ["invoice", "contract"], "pymupdf")
                if classified[path.name]["class"] != "invoice":
                    raise AssertionError(
                        "DocumentClassifier did not identify the synthetic invoice"
                    )

        check("document_classifier", document_classifier)

        if args.embedding_model:

            def embedder():
                from gaik.software_components.RAG.embedder import Embedder

                component = bounded(Embedder(config, model=args.embedding_model))
                if args.backend == "litellm":
                    component.model = LITELLM_PREFIXES[args.provider] + args.embedding_model
                vectors, documents = component.embed(["GAIK is in Helsinki.", "A second record."])
                if len(vectors) != 2 or len(documents) != 2 or not vectors[0]:
                    raise AssertionError("Embedder returned an unexpected batch shape")
                if len(vectors[0]) != len(vectors[1]):
                    raise AssertionError("Embedder returned inconsistent dimensions")
                if not all(math.isfinite(value) for vector in vectors for value in vector):
                    raise AssertionError("Embedder returned non-finite values")

            check("embedder", embedder)
            result["embedding_model"] = args.embedding_model
        result["ok"] = all(result["checks"].get(name, {}).get("ok") for name in REQUIRED_CHECKS)
    except Exception:
        # The failed check already records a sanitized diagnostic. Never print
        # provider exception text: it may contain request details or headers.
        pass
    finally:
        result["requests"] = client.calls
        result["max_requests"] = args.max_calls
        result["max_output_tokens_per_request"] = args.output_tokens
        for original in created_clients:
            with contextlib.suppress(Exception):
                _close(original)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--backend", choices=["native", "litellm"], default="native")
    parser.add_argument("--model", required=True)
    parser.add_argument("--embedding-model")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--max-calls", type=int, default=10)
    parser.add_argument("--output-tokens", type=int, default=2048)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    logging.disable(logging.CRITICAL)
    with open(os.devnull, "w") as quiet:
        with contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
            try:
                result = run_smoke(args)
            except Exception as exc:
                result = {
                    "provider": args.provider,
                    "model": args.model,
                    "backend": args.backend,
                    "ok": False,
                    "authenticated_live": False,
                    "checks": {},
                    "error_type": type(exc).__name__,
                    "status_code": getattr(exc, "status_code", None),
                }
    result["elapsed_s"] = round(time.monotonic() - started, 2)
    result["git_commit"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1], text=True
    ).strip()
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"provider": args.provider, "model": args.model, "ok": result["ok"]}))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
