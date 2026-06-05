"""RAGEvaluator demo — RAGAS-style RAG metrics built on LLMJudge v2.

Computes faithfulness, answer relevance, context precision and (optionally)
context recall, each on a 1-5 Likert scale via :class:`LLMJudge`. Aggregates
to 0-1 RAGMetrics for the dataset.

This script needs a Google Vertex / OpenAI / Anthropic API set up — change
``LLMJudge(model_provider=...)`` to whatever you have configured. Alternative:
construct ``RAGEvaluator(judge=panel)`` with an ``LLMJudgePanel`` for
cross-model averaging.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.evaluators import RAGEvaluator  # noqa: E402
from gaik.software_components.validators import LLMJudge  # noqa: E402


SAMPLE_ITEMS = [
    {
        "query": "Mihin aikaan asiakaspalvelu sulkeutuu perjantaisin?",
        "answer": "Asiakaspalvelu sulkeutuu perjantaisin klo 16.",
        "context": [
            "Asiakaspalvelu palvelee ma–to klo 8–18 ja perjantaisin klo 8–16.",
            "Sähköpostit luetaan seuraavana arkipäivänä.",
        ],
        "ground_truth": "Klo 16 perjantaisin.",
    },
    {
        "query": "Mitä asiakas voi tehdä, jos pakkaus saapuu vahingoittuneena?",
        "answer": (
            "Asiakkaan kannattaa olla yhteydessä kuljetusyhtiöön ja pyytää uutta "
            "lähetystä. Kuluja saa hyvitettyä parhaiten somessa kohun jälkeen."
        ),
        "context": [
            "Vahingoittuneista pakkauksista pyydetään ottamaan yhteyttä asiakaspalveluun "
            "kahden arkipäivän kuluessa toimituksesta.",
            "Asiakaspalvelu hoitaa korvaavan toimituksen ja vahinkoilmoituksen.",
        ],
        "ground_truth": (
            "Ottaa yhteyttä asiakaspalveluun kahden arkipäivän kuluessa, "
            "joka hoitaa korvaavan toimituksen."
        ),
    },
]


def main() -> None:
    judge = LLMJudge(
        model_provider="google",
        model="gemini-3-flash-preview",
        use_vertexai=True,
    )
    evaluator = RAGEvaluator(judge=judge)

    result = evaluator.evaluate_dataset(SAMPLE_ITEMS)

    print("=== Per-item ===\n")
    for i, r in enumerate(result.per_item):
        print(f"Item {i}: query={r.query!r}")
        print(f"  faithfulness     = {r.faithfulness_score}/5  ({r.reasons['faithfulness']})")
        print(
            f"  answer_relevance = {r.answer_relevance_score}/5  ({r.reasons['answer_relevance']})"
        )
        print(
            f"  context_precision= {r.context_precision_score}/5  ({r.reasons['context_precision']})"
        )
        if r.context_recall_score is not None:
            print(
                f"  context_recall   = {r.context_recall_score}/5  ({r.reasons['context_recall']})"
            )
        print(f"  cost             = ${r.cost_usd:.4f}")
        print()

    print("=== Aggregate ===")
    print(result.aggregate)
    print(f"Total cost: ${result.cost_usd:.4f}")


if __name__ == "__main__":
    main()
