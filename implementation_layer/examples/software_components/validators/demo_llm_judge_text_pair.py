"""LLMJudge text-vs-text equivalence demo.

Compares two short Finnish strings for semantic equivalence using
``LLMJudge.judge_text_pair`` — no source document required.

Use case: scoring an audio-transcription extractor where the extracted
free-text field paraphrases the same fact as the hand-annotated ground
truth. Exact-string matching scores those wrong; the text-pair judge
recognises them as equivalent.

Requires Azure OpenAI credentials (the default `model_provider="azure"`):
    AZURE_API_KEY, AZURE_ENDPOINT, AZURE_DEPLOYMENT, AZURE_API_VERSION
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.validators import LLMJudge  # noqa: E402


PAIRS = [
    # (field, expected, extracted, expected verdict)
    (
        "Mitä tapahtui",
        "Tietokonetta ei ollut lukittu.",
        "Tietokonetta ei oltu lukittu.",
        "ok",
    ),
    (
        "Tapahtumapaikan tarkenne",
        "kieppipeittaus",
        "kieppipeittauksessa",
        "ok",
    ),
    (
        "Mitä tapahtui",
        "Solmukiepit aiheuttavat tuotannon hidastumista.",
        "Solmukiepit lisäävät tuottavuutta.",
        "wrong",
    ),
    (
        "Päivämäärä",
        "26.8.2025",
        "2025-08-26",
        "ok",
    ),
]


def main() -> None:
    judge = LLMJudge(model_provider="azure")

    for field_name, expected, extracted, predicted in PAIRS:
        print(f"\nField: {field_name}")
        print(f"  Expected:  {expected!r}")
        print(f"  Extracted: {extracted!r}")
        verdict = judge.judge_text_pair(
            extracted_text=extracted,
            expected_text=expected,
            field_name=field_name,
        )
        match_marker = "OK   " if verdict.severity == predicted else "DIFF "
        print(
            f"  -> {match_marker} severity={verdict.severity} "
            f"score={verdict.score} equivalent={verdict.equivalent}"
        )
        print(f"     reason: {verdict.reason}")
        print(
            f"     usage: {verdict.usage.input_tokens}+{verdict.usage.output_tokens} tok, "
            f"${verdict.usage.cost_usd:.4f}, {verdict.usage.duration_s:.2f}s"
        )


if __name__ == "__main__":
    main()
