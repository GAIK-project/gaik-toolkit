"""LLMJudge.detect_hallucinations() demo — schema-agnostic post-extraction scrub.

Given a source transcript and an extractor's structured output, the judge
flags any field whose value is not directly supported by the source.

Use case: a generic alternative to handwritten keyword post-validators
(which need a separate config per schema). Drop the flagged values to
``""`` to clean up hallucinated extraction outputs.

Requires Azure OpenAI credentials (default ``model_provider="azure"``):
    AZURE_API_KEY, AZURE_ENDPOINT, AZURE_DEPLOYMENT, AZURE_API_VERSION
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.validators import LLMJudge  # noqa: E402

TRANSCRIPT = (
    "Moi, täällä Matti Möttönen. 26.8.25 kulkiessani pihalla huomasin, "
    "että alihankkijan vesikärry oli parkkeerattu esimerkillisesti "
    "väljään kohtaan pihaa."
)

# A typical extractor output: most fields grounded, two hallucinated
# (organisation guessed from domain context, suggestion invented).
EXTRACTED = {
    "tarkkailijan_nimi": "Matti Möttönen",
    "tarkkailijan_organisaatio": "Luvata Pori Oy",  # ← hallucination
    "paivamaara": "26.8.25",
    "rakennus": "Ulkoalueet",
    "tapahtumapaikan_tarkenne": "pihalla",
    "mita_tapahtui": "Vesikärry parkkeerattu hyvin.",
    "lahella_piti_tilanne": "Ei",
    "ehdotus": "Jatkossa kannattaisi merkitä myös pyöräkiilat.",  # ← invented
}


def main() -> None:
    judge = LLMJudge(model_provider="azure")
    report = judge.detect_hallucinations(
        source_text=TRANSCRIPT,
        extracted=EXTRACTED,
    )
    print(f"Source transcript:\n  {TRANSCRIPT}\n")
    print("Extracted (input):")
    for k, v in EXTRACTED.items():
        print(f"  {k}: {v!r}")
    print()
    print(f"Judge flagged {len(report.flags)} hallucinations:")
    for flag in report.flags:
        print(f"  - {flag.field} = {flag.value!r}  ({flag.severity})")
        print(f"    reason: {flag.reason}")
    print()
    print(
        f"Usage: {report.usage.input_tokens}+{report.usage.output_tokens} tokens, "
        f"${report.usage.cost_usd:.4f}, {report.usage.duration_s:.2f}s"
    )

    # Apply the scrub: clear flagged fields.
    cleaned = dict(EXTRACTED)
    for flag in report.flags:
        cleaned[flag.field] = ""

    print("\nCleaned extraction (after scrub):")
    for k, v in cleaned.items():
        marker = " ← cleared" if v == "" and EXTRACTED.get(k) else ""
        print(f"  {k}: {v!r}{marker}")


if __name__ == "__main__":
    main()
