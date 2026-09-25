"""Check Aitta through GAIK's shared client and DataExtractor.

    uv run python implementation_layer/examples/software_components/llm/example_aitta_smoke.py \
        --env-file /path/to/aitta.env

Only AITTA_* keys are read from the optional env file. By default, choose an
already-running chat model to avoid unnecessary cold starts. Use --model to
select another model, or --embedding-model to also test embeddings (which may
need a cold start). The input is synthetic; no project documents are uploaded.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values
from gaik.software_components.extractor import DataExtractor
from gaik.software_components.extractor.schema import ExtractionRequirements, FieldSpec
from gaik.software_components.llm import create_llm_client, get_llm_config
from pydantic import BaseModel, ConfigDict


class ProjectFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project: str
    city: str


def smoke(args: argparse.Namespace) -> dict:
    overrides = {"timeout": args.timeout, "max_retries": 0}
    if args.env_file:
        values = dotenv_values(args.env_file)
        token = next(
            (
                values[k]
                for k in ("AITTA_API_KEY", "AITTA_API_TOKEN", "AITTA_TOKEN")
                if values.get(k)
            ),
            None,
        )
        if not token:
            raise ValueError("The env file must contain an Aitta API key")
        overrides["api_key"] = token
        if values.get("AITTA_BASE_URL"):
            overrides["base_url"] = values["AITTA_BASE_URL"]
    config = get_llm_config("aitta", **overrides)
    # This example targets CSC's service. Keep its token on the documented host.
    if str(config["base_url"]).rstrip("/") != "https://aitta-api.csc.fi/openai/v1":
        raise ValueError("This smoke example requires CSC's documented Aitta base URL")
    with httpx.Client(
        base_url="https://aitta-api.csc.fi",
        headers={"Authorization": f"Bearer {config['api_key']}"},
        timeout=30,
    ) as metadata:
        models_response = metadata.get("/model")
        models_response.raise_for_status()
        models = [item["name"] for item in models_response.json()["_links"]["item"]]
        workers_response = metadata.get("/worker")
        workers_response.raise_for_status()
        running = {
            worker["model"]
            for worker in workers_response.json().get("_embedded", {}).get("workers", [])
            if worker["status"] == "running"
        }
        selected = args.model
        if not selected:
            for model in models:
                if model not in running:
                    continue
                details = metadata.get(f"/model/{model.replace('/', '~')}")
                details.raise_for_status()
                if "openai-chat-completion" in details.json().get("capabilities", []):
                    selected = model
                    break
        if not selected:
            raise RuntimeError("No chat model is running; select --model for a cold start")
        if selected not in models:
            raise ValueError("The selected model is not in Aitta's current catalog")

    config["model"] = selected
    result = {"provider": "aitta", "model": selected, "catalog_count": len(models)}
    print(json.dumps(result), flush=True)
    client = create_llm_client(config)
    try:
        response = client.chat(
            [{"role": "user", "content": "Reply with only the word OK."}],
            max_tokens=128,
        )
        if not response.text.strip():
            raise RuntimeError("Chat returned no text")
        result["chat"] = response.text.strip()
        streamed = "".join(
            client.chat_stream(
                [{"role": "user", "content": "Reply with only the word OK."}],
                max_tokens=128,
            )
        )
        if not streamed.strip():
            raise RuntimeError("Stream returned no text")
        result["stream"] = streamed.strip()

        document = "Project: GAIK. City: Helsinki."
        fact = client.chat_parsed(
            [{"role": "user", "content": f"Extract project and city from: {document}"}],
            response_format=ProjectFact,
            max_tokens=256,
        )
        expected = {"project": "GAIK", "city": "Helsinki"}
        if fact.model_dump() != expected:
            raise RuntimeError("Structured output did not match the synthetic input")
        result["structured_output"] = fact.model_dump()
        requirements = ExtractionRequirements(
            use_case_name="aitta_smoke",
            fields=[
                FieldSpec(field_name=name, field_type="str", description=name) for name in expected
            ],
        )
        extractor = DataExtractor(config=config)
        try:
            records = extractor.extract(
                extraction_model=ProjectFact,
                requirements=requirements,
                user_requirements="Extract project and city exactly as written.",
                documents=[document],
            )
        finally:
            extractor.client.raw.close()
        if records != [expected]:
            raise RuntimeError("DataExtractor did not match the synthetic input")
        result["data_extractor"] = records

        if args.embedding_model:
            vectors = client.embed(
                ["query: What is GAIK?", "passage: GAIK is an AI toolkit."],
                model=args.embedding_model,
            )
            if len(vectors) != 2 or not vectors[0] or len(vectors[0]) != len(vectors[1]):
                raise RuntimeError("Embeddings have an unexpected shape")
            result["embeddings"] = {
                "model": args.embedding_model,
                "count": len(vectors),
                "dimensions": len(vectors[0]),
            }
        return result
    finally:
        client.raw.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--model", help="Explicit model; otherwise use a running chat model")
    parser.add_argument("--embedding-model", help="Optional embedding model from /model")
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    start = time.monotonic()
    try:
        result = smoke(args)
    except Exception as exc:
        # Avoid dumping request headers, config dictionaries, or provider error bodies.
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": type(exc).__name__,
                    "status_code": getattr(exc, "status_code", None),
                }
            )
        )
        return 1
    result.update(ok=True, elapsed_s=round(time.monotonic() - start, 2))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
