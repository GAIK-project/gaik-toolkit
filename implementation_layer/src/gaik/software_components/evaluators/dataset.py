"""Tiny dataset abstraction used by all evaluators.

Plain dataclass + JSONL/CSV readers so consumers can keep their evaluation
data wherever they like. No pandas dependency; we only need iteration.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EvaluationItem:
    """One row of an evaluation dataset.

    The shape is intentionally generic so the same dataset can drive an
    extraction or RAG evaluation. Only ``input`` is required.

    Attributes:
        input: The pipeline input — extractor source text, RAG query, etc.
            Free-form (str / dict / list).
        expected: Ground-truth output to compare against. For extraction
            usually ``dict`` of expected fields; for RAG, the reference
            answer string. ``None`` when no ground truth is available.
        context: Retrieved or supplied context passages, used by
            :class:`gaik.software_components.evaluators.RAGEvaluator`.
        metadata: Arbitrary key/value pairs (item id, source, vendor, etc.).
    """

    input: Any
    expected: Any = None
    context: list[str] | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class EvaluationDataset:
    """Iterable container of :class:`EvaluationItem`.

    Use the classmethods to load from disk; use :meth:`from_list` for
    in-memory constructions in tests / notebooks.
    """

    items: list[EvaluationItem]

    def __iter__(self) -> Iterator[EvaluationItem]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, idx: int) -> EvaluationItem:
        return self.items[idx]

    @classmethod
    def from_list(cls, items: Iterable[dict | EvaluationItem]) -> EvaluationDataset:
        out: list[EvaluationItem] = []
        for raw in items:
            if isinstance(raw, EvaluationItem):
                out.append(raw)
            else:
                out.append(_item_from_dict(raw))
        return cls(items=out)

    @classmethod
    def from_jsonl(cls, path: str | Path) -> EvaluationDataset:
        path = Path(path)
        items: list[EvaluationItem] = []
        with path.open(encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSON on {path}:{line_no}: {exc}"
                    ) from exc
                items.append(_item_from_dict(raw))
        return cls(items=items)

    @classmethod
    def from_csv(cls, path: str | Path) -> EvaluationDataset:
        path = Path(path)
        items: list[EvaluationItem] = []
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                items.append(_item_from_dict(dict(row)))
        return cls(items=items)


def _item_from_dict(raw: dict) -> EvaluationItem:
    if "input" not in raw:
        raise ValueError(f"Evaluation row is missing required 'input' field: {raw}")
    context = raw.get("context")
    if isinstance(context, str):
        # CSV columns come back as strings — split on \n if it looks pre-joined.
        context = [s for s in context.split("\n") if s.strip()] or None
    metadata = raw.get("metadata", {}) or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {"_raw": metadata}
    return EvaluationItem(
        input=raw["input"],
        expected=raw.get("expected"),
        context=context,
        metadata=metadata,
    )
