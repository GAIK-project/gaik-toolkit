"""Bounded, authenticated component smoke test used by release_check.py.

All prompts, documents and audio are synthetic. No response bodies, credentials, or
exception messages are written to the result. This is a real provider test,
not a credential-presence check; every required component must return a
semantically correct result for the selected model.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import logging
import math
import os
import subprocess
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REQUIRED_CHECKS = (
    "chat",
    "stream",
    "schema_generator",
    "data_extractor",
    "source_tracing",
    "answer_generator",
    "document_classifier",
    "report_writing",
)

LITELLM_PREFIXES = {
    "azure": "azure/",
    "openai": "openai/",
    "aitta": "openai/",
    "google": "gemini/",
    "anthropic": "anthropic/",
}

# Synthetic Finnish speech, two sentences with a pause between them; see
# release_fixtures/README.md. The anchors are stems of words in each sentence.
TRANSCRIPTION_FIXTURE = Path(__file__).resolve().parent / "release_fixtures/transcription_fi.mp3"
TRANSCRIPTION_FIXTURE_SHA256 = "b5d6cde7d4bc107344f41a2eb8af2eef9c87340acce07ec4347ea25b98b703c5"
TRANSCRIPTION_FIRST_SENTENCE = ("huoltoteknik", "ilmoitta", "pumppu", "kattilahuone")
TRANSCRIPTION_SECOND_SENTENCE = ("havaittiin", "maanantai", "yhdeksän", "korkea")
# A transcript may mishear one word of a sentence, but not lose the sentence.
TRANSCRIPTION_MIN_ANCHORS = 3
# Caller context for the chunked run: a name in the audio's language.
TRANSCRIPTION_CONTEXT = "Matti Virtanen"
# Splits the 12.8-second fixture into two requests, in the pause between the sentences.
TRANSCRIPTION_CHUNK_SECONDS = 8


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

    def count(self):
        """Take one request from the allowance."""
        if self.calls >= self.max_calls:
            raise RuntimeError("Live release request budget exceeded")
        self.calls += 1

    def options(self, provider, kwargs, *, embedding=False):
        self.count()
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

    @property
    def usage(self):
        return self._client.usage

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


class BoundedAudioClient:
    """Count transcription requests against the shared budget and keep what was sent.

    The prompt and the transcript of each request stay in memory for the check's own
    assertions; neither is written to the result. Each request still goes through the
    raw SDK client the Transcriber constructed, with the arguments it chose.
    """

    def __init__(self, raw, budget):
        self.raw = raw
        self.requests = []

        def create(**kwargs):
            budget.count()
            request = {"has_prompt": "prompt" in kwargs, "prompt": kwargs.get("prompt")}
            self.requests.append(request)
            response = raw.audio.transcriptions.create(**kwargs)
            request["text"] = response.text
            return response

        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=create))

    def close(self):
        _close(self.raw)


def _anchor_hits(text, anchors):
    lowered = (text or "").lower()
    return sum(anchor in lowered for anchor in anchors)


def transcription_check(config, transcription_model, budget, work_dir) -> dict:
    """Transcribe the synthetic Finnish fixture with the default Transcriber, once in a
    single request and once in two chunks with caller context, and check what each
    request sent and returned. Returns a sanitized observation."""
    import gaik.software_components.transcriber.transcriber as transcriber_module
    from gaik.software_components.transcriber import Transcriber

    digest = hashlib.sha256(TRANSCRIPTION_FIXTURE.read_bytes()).hexdigest()
    if digest != TRANSCRIPTION_FIXTURE_SHA256:
        raise AssertionError("The synthetic transcription fixture changed")
    audio_config = {**config, "transcription_model": transcription_model}
    original = transcriber_module._create_audio_client

    def transcribe(name, call=None, **options):
        clients = []

        def bounded_audio_client(api_config):
            clients.append(BoundedAudioClient(original(api_config), budget))
            return clients[-1]

        with mock.patch.object(transcriber_module, "_create_audio_client", bounded_audio_client):
            result = Transcriber(
                api_config=audio_config, output_dir=Path(work_dir) / name, **options
            ).transcribe(TRANSCRIPTION_FIXTURE, **(call or {}))
        requests = [request for client in clients for request in client.requests]
        # The chunked path records a failed request in the transcript instead of raising.
        if "[Transcription failed" in result.raw_transcript or any(
            "text" not in request for request in requests
        ):
            raise AssertionError(f"A {name} transcription request failed")
        return result, requests

    def require_sentence(text, anchors, what):
        if _anchor_hits(text, anchors) < TRANSCRIPTION_MIN_ANCHORS:
            raise AssertionError(f"The {what} lost a sentence of the Finnish audio")

    single, single_requests = transcribe("single")
    if len(single_requests) != 1 or single_requests[0]["has_prompt"]:
        raise AssertionError("A default Transcriber did not send one request without a prompt")
    require_sentence(single_requests[0]["text"], TRANSCRIPTION_FIRST_SENTENCE, "transcript")
    require_sentence(single_requests[0]["text"], TRANSCRIPTION_SECOND_SENTENCE, "transcript")

    chunked, chunk_requests = transcribe(
        "chunked",
        call={"custom_context": TRANSCRIPTION_CONTEXT},
        max_duration_seconds=TRANSCRIPTION_CHUNK_SECONDS,
    )
    if len(chunk_requests) != 2:
        raise AssertionError("The fixture was not transcribed in two chunks")
    first, second = chunk_requests
    if first["prompt"] != TRANSCRIPTION_CONTEXT:
        raise AssertionError("The first chunk did not carry the caller's context")
    # The second request continues from the end of the first chunk's transcript.
    if not second["has_prompt"] or not second["prompt"].endswith(first["text"][-50:]):
        raise AssertionError("The second chunk did not continue from the first transcript")
    require_sentence(first["text"], TRANSCRIPTION_FIRST_SENTENCE, "first chunk")
    require_sentence(second["text"], TRANSCRIPTION_SECOND_SENTENCE, "second chunk")

    return {
        "fixture_sha256": digest,
        "single_requests": len(single_requests),
        "single_request_has_prompt": False,
        "chunk_requests": len(chunk_requests),
        "second_chunk_prompt_has_context": second["prompt"].startswith(TRANSCRIPTION_CONTEXT),
        "anchor_hits": {
            "single": [
                _anchor_hits(single_requests[0]["text"], TRANSCRIPTION_FIRST_SENTENCE),
                _anchor_hits(single_requests[0]["text"], TRANSCRIPTION_SECOND_SENTENCE),
            ],
            "chunks": [
                _anchor_hits(first["text"], TRANSCRIPTION_FIRST_SENTENCE),
                _anchor_hits(second["text"], TRANSCRIPTION_SECOND_SENTENCE),
            ],
            "of": len(TRANSCRIPTION_FIRST_SENTENCE),
        },
        "usage": {"single": single.usage, "chunked": chunked.usage},
    }


def smoke_config(provider: str, model: str, timeout: float, backend: str = "native") -> dict:
    """The config the smoke test runs with.

    Every provider gets the run's timeout and no retries, except Vertex AI with
    no location set: it runs with the defaults a user gets, so the run certifies
    the EU request's own limit, its single attempt and the global fallback.
    """
    from gaik.software_components.llm import get_llm_config

    config = get_llm_config(provider, model=model)
    if provider == "vertex" and backend == "native" and config.get("location_fallback"):
        return config
    return get_llm_config(provider, model=model, timeout=timeout, max_retries=0)


def vertex_locations(clients) -> list[str]:
    """The Vertex AI locations the run's clients last answered from."""
    found = set()
    for client in clients:
        client = getattr(client, "_client", client)
        if getattr(client, "provider", None) == "vertex" and getattr(client, "location", None):
            found.add(client.location)
    return sorted(found)


def run_smoke(args) -> dict:
    from gaik.software_components.llm import create_llm_client

    config = smoke_config(args.provider, args.model, args.timeout, args.backend)
    if args.provider == "aitta":
        if str(config["base_url"]).rstrip("/") != "https://aitta-api.csc.fi/openai/v1":
            raise ValueError("Aitta release checks require CSC's documented endpoint")
    # The Transcriber calls the provider's audio API directly, never through LiteLLM.
    native_config = config
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
        "vertex_default_location": bool(
            args.provider == "vertex"
            and args.backend == "native"
            and native_config.get("location_fallback")
        ),
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

        def source_tracing():
            from gaik.software_components.source_tracing import SourceTracing

            document = "Project: GAIK. City: Helsinki."
            tracing = SourceTracing()
            task = tracing.augment(
                generated["model"],
                "Extract the project name and the city, exactly as written in the document.",
                source="text",
            )
            records = bounded(DataExtractor(config)).extract(
                extraction_model=task.model,
                requirements=generator.item_requirements,
                user_requirements=task.prompt,
                documents=[document],
            )
            clean, report = tracing.check_text(records, [document])
            summary = report.summary()
            result["source_tracing_observation"] = {
                key: summary[key] for key in ("verified", "check", "reworded", "unchecked", "total")
            }
            if clean != [{"project": "GAIK", "city": "Helsinki"}]:
                raise AssertionError("Source tracing changed the extracted record")
            if summary["verified"] != 2 or summary["total"] != 2 or summary["coverage"] != 1.0:
                raise AssertionError("The extractor did not return verifiable evidence")

        check("source_tracing", source_tracing)

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

        def report_writing():
            import gaik.software_components.draft_reviewer.draft_reviewer as reviewer_module
            import gaik.software_components.report_synthesizer.report_synthesizer as writer_module
            from gaik.software_components.draft_reviewer import DraftReviewer
            from gaik.software_components.knowledge_curator import KnowledgeCurator, SectionSpec
            from gaik.software_components.report_synthesizer import ReportSynthesizer
            from gaik.software_components.source_normalizer import NormalizedSources

            sources = NormalizedSources.from_texts(
                {
                    "site_notes.txt": "Site visit on 14 March 2026. The heat pump in the "
                    "utility room was installed in 2019 and ran quietly."
                },
                source_class="primary",
            )
            sections = [
                SectionSpec(
                    id="heating",
                    title="Heating",
                    instructions="Describe the heating system.",
                    required_items=["heating system", "latest chimney inspection"],
                )
            ]
            knowledge = bounded(KnowledgeCurator(config)).curate(sources, sections)
            heating = knowledge.get("heating")
            if not heating.units or any(u.source.file != "site_notes.txt" for u in heating.units):
                raise AssertionError("KnowledgeCurator did not cite the synthetic source")
            if not any("chimney" in item.lower() for item in heating.missing):
                raise AssertionError("KnowledgeCurator did not list the missing item")

            review = bounded(DraftReviewer(config)).review(
                "The heat pump was installed in 2015.",
                reference="The heat pump was installed in 2019.",
            )
            if "2019" not in review.text or "2015" in review.text:
                raise AssertionError("DraftReviewer did not correct the planted year")

            # ReportSynthesizer creates its writer and reviewer clients per call.
            def budgeted_client(component_config):
                original = create_llm_client(component_config)
                created_clients.append(original)
                return BoundedClient(original, budget=client.budget)

            with (
                mock.patch.object(writer_module, "create_llm_client", budgeted_client),
                mock.patch.object(reviewer_module, "create_llm_client", budgeted_client),
            ):
                report = ReportSynthesizer(config).synthesize(
                    knowledge, sections, title="Synthetic heating check"
                )
            text = report.sections[0].text
            if "2019" not in text or "(missing:" not in text:
                raise AssertionError("ReportSynthesizer lost the fact or the missing marker")

        check("report_writing", report_writing)

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

        if args.transcription_model:

            def transcription():
                with tempfile.TemporaryDirectory(prefix="gaik-release-transcription-") as temp:
                    result["transcription_observation"] = transcription_check(
                        native_config, args.transcription_model, client.budget, Path(temp)
                    )

            check("transcription", transcription)
            result["transcription_model"] = args.transcription_model
        result["ok"] = all(result["checks"].get(name, {}).get("ok") for name in REQUIRED_CHECKS)
    except Exception:
        # The failed check already records a sanitized diagnostic. Never print
        # provider exception text: it may contain request details or headers.
        pass
    finally:
        result["requests"] = client.calls
        result["max_requests"] = args.max_calls
        result["max_output_tokens_per_request"] = args.output_tokens
        if args.provider == "vertex":
            # Which endpoint answered: "eu", or "global" after a fallback.
            result["vertex_locations"] = vertex_locations(created_clients)
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
    parser.add_argument(
        "--transcription-model",
        help="Transcription model or Azure deployment; adds the transcription check",
    )
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--max-calls", type=int, default=24)
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
