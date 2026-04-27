"""Bare ProviderClient usage: chat, chat_parsed, chat_stream, embed.

Demonstrates the four core methods of ``gaik.software_components.llm``'s
``ProviderClient`` against whichever providers have env vars set. Useful as
a copy-paste starting point for new components or one-off scripts that need
direct multi-provider access without going through ``DataExtractor`` etc.

Run with at least one of: ``AZURE_API_KEY``+``AZURE_ENDPOINT``,
``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``, ``GOOGLE_API_KEY``
(or ``GEMINI_API_KEY``).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from pydantic import BaseModel, ConfigDict, Field  # noqa: E402

from gaik.software_components.llm import create_llm_client, get_llm_config  # noqa: E402


class CountryFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(description="Country name")
    capital: str = Field(description="Capital city")
    population_millions: float = Field(description="Population in millions, approximate")


def available_providers() -> list[str]:
    candidates: list[str] = []
    if os.getenv("AZURE_API_KEY") and os.getenv("AZURE_ENDPOINT"):
        candidates.append("azure")
    elif os.getenv("OPENAI_API_KEY"):
        candidates.append("openai")
    if os.getenv("ANTHROPIC_API_KEY"):
        candidates.append("anthropic")
    if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
        candidates.append("google")
    return candidates


def demo_chat(client) -> None:
    print("\n[chat] one-shot completion")
    response = client.chat(
        messages=[
            {"role": "system", "content": "You answer in one sentence."},
            {"role": "user", "content": "Why is the sky blue?"},
        ],
    )
    print(f"  text: {response.text[:120]}...")
    print(f"  usage: {response.usage}")


def demo_chat_stream(client) -> None:
    print("\n[chat_stream] streaming deltas")
    stream = client.chat_stream(
        messages=[
            {"role": "user", "content": "Count from one to five, one per line."},
        ],
    )
    print("  ", end="", flush=True)
    for delta in stream:
        print(delta, end="", flush=True)
    print()


def demo_chat_parsed(client) -> None:
    print("\n[chat_parsed] Pydantic structured output")
    fact = client.chat_parsed(
        messages=[
            {"role": "system", "content": "Return one factual record about a country."},
            {"role": "user", "content": "Tell me about Finland."},
        ],
        response_format=CountryFact,
    )
    print(f"  {fact}")


def demo_embed(client) -> None:
    print("\n[embed] batch embeddings")
    try:
        vectors = client.embed(["Hello world", "Greetings everyone"])
        print(f"  {len(vectors)} vectors, dim={len(vectors[0])}")
    except NotImplementedError as exc:
        print(f"  (skipped) {exc}")


def main() -> None:
    providers = available_providers()
    if not providers:
        print(
            "No provider env vars set. Set at least one of: AZURE_API_KEY, "
            "OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY."
        )
        return

    for provider in providers:
        print("\n" + "=" * 70)
        print(f"Provider: {provider}")
        print("=" * 70)
        try:
            client = create_llm_client(get_llm_config(provider))
            demo_chat(client)
            demo_chat_stream(client)
            demo_chat_parsed(client)
            demo_embed(client)
        except Exception as exc:
            print(f"  [SKIP] {provider}: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
