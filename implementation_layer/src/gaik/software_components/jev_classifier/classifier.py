"""
Text and document classification with the Jev model (TypeSafe System One).

Jev answers a Choice question with the chosen label plus a probability for every
label and a confidence. This module wraps that into a classifier that returns a
label, the probabilities behind it, and an optional "unknown" or broader-label
fallback when the model is not confident.
"""

import logging
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "jev-1.13.0"
DEFAULT_INSTRUCTIONS = "Which label best describes the text?"
UNKNOWN = "unknown"
_QUESTION_ID = "label"
_SUPPORTED_SUFFIXES = {".pdf", ".docx", ".doc"}


def _normalize_classes(classes: Sequence[str] | Mapping[str, str | None]) -> dict[str, str | None]:
    """Turn a list of labels or a {label: description} mapping into an ordered dict."""
    if isinstance(classes, Mapping):
        normalized = {str(label): description for label, description in classes.items()}
    else:
        normalized = {str(label): None for label in classes}
    if len(normalized) < 2:
        raise ValueError("classes needs at least two distinct labels")
    if any(not label.strip() for label in normalized):
        raise ValueError("class labels must not be empty")
    return normalized


class JevClassifier:
    """
    Classify text or documents into predefined classes with Jev.

    Jev is TypeSafe's System One model. It returns typed answers with calibrated
    probabilities instead of generated text, so the classifier can tell a clear
    case from a doubtful one and the caller decides what to do with the doubtful ones.

    Text sent to this classifier leaves your infrastructure for TypeSafe (United
    States). Send only what the decision needs, and no sensitive personal data.
    GAIK applications should not hold their own TypeSafe key: point ``base_url`` at
    the ``gaik-decide`` service and use the per-app key it issues.

    Attributes:
        model: Pinned Jev model version, e.g. ``"jev-1.13.0"``.
        client: The ``typesafe_sdk.TypeSafeClient`` used for requests.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        model: str = DEFAULT_MODEL,
        timeout: float = 30.0,
        max_retries: int = 3,
        client: Any = None,
    ):
        """
        Initialize the classifier.

        Args:
            api_key: TypeSafe API key, or the gaik-decide key when ``base_url``
                points at gaik-decide. Passed in by the caller; never read from the
                environment here.
            base_url: API root. ``None`` uses TypeSafe directly. For gaik-decide pass
                its root URL (without ``/v1``).
            model: Pinned Jev model version. A partial version such as ``jev-1.13``
                is rejected by the API.
            timeout: Request timeout in seconds.
            max_retries: Retries for 429 and 5xx responses, handled by the SDK.
            client: A ready-made ``TypeSafeClient`` (or a compatible object with a
                ``system_one`` method). When given, ``api_key`` and ``base_url`` are
                not used to build a client. Meant for tests and custom transports.

        Raises:
            ValueError: If ``api_key`` is empty and no ``client`` is given.
            ImportError: If ``typesafe-sdk`` is not installed.

        Example:
            >>> from gaik.software_components.jev_classifier import JevClassifier
            >>> classifier = JevClassifier(
            ...     api_key=gaik_decide_key,
            ...     base_url="https://gaik-decide.2.rahtiapp.fi",
            ... )
        """
        self.model = model
        if client is not None:
            self.client = client
            return
        if not api_key or not api_key.strip():
            raise ValueError("api_key is required (pass your gaik-decide or TypeSafe key)")
        try:
            from typesafe_sdk import RetryPolicy, TypeSafeClient
        except ImportError as e:
            raise ImportError(
                "JevClassifier needs the TypeSafe SDK. "
                "Install it with: pip install gaik[jev-classifier]"
            ) from e
        self.client = TypeSafeClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
            retry=RetryPolicy(max_retries=max_retries),
        )

    def classify(
        self,
        text: str,
        classes: Sequence[str] | Mapping[str, str | None],
        instructions: str | None = None,
        min_confidence: float | None = None,
        hierarchy: Mapping[str, str] | None = None,
        max_chars: int = 10_000,
    ) -> dict:
        """
        Classify one text.

        Args:
            text: The text to classify.
            classes: Class labels, or a ``{label: description}`` mapping. Descriptions
                are passed to Jev as the meaning of each option and clearly improve
                accuracy when labels are terse or overlap.
            instructions: The question put to Jev. Defaults to a generic
                "which label best describes the text" question. State the task and the
                distinction that matters, for example "Which kind of document is this?"
            min_confidence: If given and Jev's confidence is below it, the result is
                ``"unknown"`` (or the parent label when ``hierarchy`` is given).
                Confidence is separate from probability: it is high when nearly all
                probability landed on one label. Start at 0.9 and tune on labelled data.
            hierarchy: Optional ``{label: broader_label}`` mapping. When confidence is
                below ``min_confidence``, the broader label is reported instead of
                ``"unknown"``. The broader label follows from the narrow one, so no
                second request is made.
            max_chars: Input is cut to this many characters (the API accepts at most
                50,000).

        Returns:
            ``{"class", "confidence", "probabilities", "predicted", "model"}``.
            ``predicted`` is Jev's top label; ``class`` equals it unless the confidence
            gate replaced it.

        Raises:
            ValueError: If ``text`` is empty or ``classes`` is invalid.
            typesafe_sdk.TypeSafeError: If the request fails after retries.

        Example:
            >>> classifier.classify(
            ...     "Invoice 4412, total 1 240 EUR, due 30 days",
            ...     classes={"invoice": "bill asking for payment", "receipt": "proof of payment"},
            ...     min_confidence=0.9,
            ... )
        """
        if not text or not text.strip():
            raise ValueError("text must not be empty")
        if not 1 <= max_chars <= 50_000:
            raise ValueError("max_chars must be between 1 and 50000")
        if min_confidence is not None and not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")

        criteria = _normalize_classes(classes)
        if hierarchy:
            unknown_children = set(hierarchy) - set(criteria)
            if unknown_children:
                raise ValueError(
                    f"hierarchy names labels not in classes: {sorted(unknown_children)}"
                )

        from typesafe_sdk import Choice

        response = self.client.system_one(
            text.strip()[:max_chars],
            {
                _QUESTION_ID: Choice(
                    instructions=instructions or DEFAULT_INSTRUCTIONS,
                    criteria=criteria,
                )
            },
        )
        answer = response.choices[_QUESTION_ID]
        predicted = answer.choice
        label = predicted
        if min_confidence is not None and answer.confidence < min_confidence:
            label = (hierarchy or {}).get(predicted, UNKNOWN)

        return {
            "class": label,
            "confidence": answer.confidence,
            "probabilities": dict(answer.probabilities),
            "predicted": predicted,
            "model": response.model,
        }

    def classify_many(
        self,
        texts: Sequence[str],
        classes: Sequence[str] | Mapping[str, str | None],
        max_workers: int = 4,
        **kwargs: Any,
    ) -> list[dict]:
        """
        Classify several texts concurrently. Order is preserved.

        A text that fails (empty, or the request errors after retries) yields
        ``{"class": "unknown", "confidence": 0.0, "error": "..."}`` instead of
        aborting the batch. Keep ``max_workers`` modest: the API allows 1,200
        requests per minute.

        Args:
            texts: The texts to classify.
            classes: As in :meth:`classify`.
            max_workers: Concurrent requests.
            **kwargs: Passed to :meth:`classify` (``instructions``, ``min_confidence``,
                ``hierarchy``, ``max_chars``).
        """
        _normalize_classes(classes)  # fail fast on bad classes, not once per item

        def one(text: str) -> dict:
            try:
                return self.classify(text, classes, **kwargs)
            except Exception as e:
                logger.error("Classification failed: %s", e)
                return {
                    "class": UNKNOWN,
                    "confidence": 0.0,
                    "probabilities": {},
                    "predicted": UNKNOWN,
                    "model": self.model,
                    "error": str(e)[:200],
                }

        with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
            return list(pool.map(one, texts))

    def classify_file(
        self,
        file_or_dir: str,
        classes: Sequence[str] | Mapping[str, str | None],
        **kwargs: Any,
    ) -> dict:
        """
        Classify PDF or Word documents from their text.

        Reads the first ``max_chars`` characters (default 10,000) of each document with
        the PyMuPDF or python-docx parsers. Images are not supported: Jev takes text.
        Scanned PDFs without a text layer come back as ``"unknown"``.

        Args:
            file_or_dir: A single file or a directory of files.
            classes: As in :meth:`classify`.
            **kwargs: Passed to :meth:`classify`.

        Returns:
            ``{filename: result}`` with the same result shape as :meth:`classify`.

        Raises:
            FileNotFoundError: If the path does not exist.
            ValueError: If a single file has an unsupported format, or a directory
                has no supported files.
        """
        path = Path(file_or_dir)
        if not path.exists():
            raise FileNotFoundError(f"Path does not exist: {file_or_dir}")
        if path.is_file():
            files = [path]
        else:
            files = sorted(f for f in path.iterdir() if f.suffix.lower() in _SUPPORTED_SUFFIXES)
            if not files:
                raise ValueError(
                    f"No supported files in {file_or_dir}. Supported: .pdf, .docx, .doc"
                )
        if path.is_file() and path.suffix.lower() not in _SUPPORTED_SUFFIXES:
            raise ValueError(
                f"Unsupported file format: {path.suffix}. Supported: .pdf, .docx, .doc"
            )

        _normalize_classes(classes)
        results = {}
        for file in files:
            try:
                text = self._extract_text(file)
                if not text.strip():
                    results[file.name] = {
                        "class": UNKNOWN,
                        "confidence": 0.0,
                        "probabilities": {},
                        "predicted": UNKNOWN,
                        "model": self.model,
                        "error": "No text content found in document",
                    }
                    continue
                results[file.name] = self.classify(text, classes, **kwargs)
            except Exception as e:
                if path.is_file():
                    raise
                logger.error("Skipping %s: %s", file.name, e)
                results[file.name] = {
                    "class": UNKNOWN,
                    "confidence": 0.0,
                    "probabilities": {},
                    "predicted": UNKNOWN,
                    "model": self.model,
                    "error": str(e)[:200],
                }
        return results

    @staticmethod
    def _extract_text(file: Path) -> str:
        """Extract the text of a PDF or Word document."""
        if file.suffix.lower() == ".pdf":
            from ..parsers.pymypdf import PyMuPDFParser

            return PyMuPDFParser().parse_document(str(file))["text_content"]
        from ..parsers.docx_parser import DocxParser

        return DocxParser().parse_document(str(file))["text_content"]
