"""Jev Classifier Example

Classifies short texts with Jev through the gaik-decide service and shows the confidence
gate. Needs GAIK_DECIDE_URL and GAIK_DECIDE_API_KEY in the environment (or a .env file).
"""

import os
import sys
from pathlib import Path

# Load environment variables from .env file BEFORE importing gaik modules
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.jev_classifier import JevClassifier

CLASSES = {
    "invoice": "asks the reader to pay an amount by a due date",
    "receipt": "proof that a payment was made",
    "contract": "terms that two parties agree to",
    "complaint": "a customer reporting a problem",
}

TEXTS = [
    "Invoice 4412: total 1 240 EUR, due in 30 days, reference 88213.",
    "Thank you for your payment of 19.90 EUR on 3 March, card ending 4421.",
    "The parties agree that the supplier delivers the goods within 14 days.",
    "I was charged twice for the same order and nobody answers my emails.",
    "Attached are the slides from Tuesday.",
]


def build_classifier() -> JevClassifier:
    """The key is the per-app gaik-decide key, never a TypeSafe key."""
    return JevClassifier(
        api_key=os.environ["GAIK_DECIDE_API_KEY"],
        base_url=os.environ["GAIK_DECIDE_URL"],
    )


def single_text(classifier: JevClassifier):
    print("=" * 60)
    print("Single text with the confidence gate")
    print("=" * 60)
    result = classifier.classify(
        TEXTS[0],
        CLASSES,
        instructions="Which kind of business document is this?",
        min_confidence=0.9,
    )
    print(f"Class: {result['class']} (confidence {result['confidence']:.2f})")
    for label, probability in sorted(result["probabilities"].items(), key=lambda p: -p[1]):
        print(f"  {label}: {probability:.2f}")


def batch(classifier: JevClassifier):
    print("\n" + "=" * 60)
    print("Batch: unsure answers become 'unknown'")
    print("=" * 60)
    results = classifier.classify_many(
        TEXTS,
        CLASSES,
        instructions="Which kind of business document is this?",
        min_confidence=0.9,
    )
    for text, result in zip(TEXTS, results, strict=True):
        gated = " (gated)" if result["class"] != result["predicted"] else ""
        print(f"{result['class']:<10} {result['confidence']:.2f}{gated}  {text[:55]}")


if __name__ == "__main__":
    jev = build_classifier()
    single_text(jev)
    batch(jev)
