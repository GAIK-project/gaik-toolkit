"""Jev Classifier

Classify text or documents into predefined classes with Jev, TypeSafe's System One
model. Jev returns a label together with a probability for every label and a
confidence, so doubtful cases can be routed to a person, marked "unknown", or
reported at a broader level.

Main Classes:
    - JevClassifier: Classify text, batches of text, or PDF/Word files

Features:
    - Single-label classification with per-label probabilities
    - Class descriptions passed to the model as the meaning of each option
    - Confidence gate: "unknown", or a broader label from a hierarchy, below a threshold
    - Concurrent batch classification with per-item error isolation
    - Works through the gaik-decide service, so applications need no TypeSafe key

Privacy:
    Text leaves your infrastructure for TypeSafe (United States). Send only what the
    decision needs, and no sensitive personal data.

Example:
    >>> from gaik.software_components.jev_classifier import JevClassifier
    >>> classifier = JevClassifier(
    ...     api_key=gaik_decide_key,
    ...     base_url="https://gaik-decide.2.rahtiapp.fi",
    ... )
    >>> classifier.classify(
    ...     "Invoice 4412, total 1 240 EUR, due in 30 days",
    ...     classes={"invoice": "asks for payment", "receipt": "proof of payment"},
    ...     min_confidence=0.9,
    ... )
    {'class': 'invoice', 'confidence': 0.97, 'probabilities': {...},
     'predicted': 'invoice', 'model': 'jev-1.13.0'}
"""

from .classifier import DEFAULT_MODEL, JevClassifier

__all__ = ["JevClassifier", "DEFAULT_MODEL"]

__version__ = "0.1.0"
