"""Decide whether a retrieval result means anything, and calibrate the threshold.

A vector index answers every query. Ask it for nonsense and it returns its nearest
neighbours, ranked, with scores — a full page of results that looks exactly like a
page of real answers. So *result count is not evidence*: on one measured corpus a
gibberish string came back with 24 results while a real domain question came back
with 12.

What does discriminate is the distance to the closest match. Real questions land
close to something; unanswerable ones land far from everything, and on a corpus
worth searching the two populations separate cleanly enough to put a threshold
between them.

That threshold is not a constant. It is a reading off *one* embedding model
against *one* corpus, so :meth:`RelevanceGate.calibrate` exists to take the
reading — and to say so when there is no gap to put a threshold in, which is the
answer that saves you from shipping a number that splits the difference between
two overlapping populations.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = ["RelevanceGate", "Calibration"]


@dataclass(frozen=True)
class Calibration:
    """What :meth:`RelevanceGate.calibrate` read off two labelled populations.

    Attributes:
        floor: Suggested threshold, midway through the gap. ``None`` when the
            populations overlap and no threshold separates them.
        separated: Whether the two populations are disjoint.
        worst_answerable: The answerable score furthest from its query.
        best_unanswerable: The unanswerable score closest to its query.
        margin: Size of the gap. Negative when they overlap, and the magnitude is
            then how far into each other they reach.
    """

    floor: float | None
    separated: bool
    worst_answerable: float
    best_unanswerable: float
    margin: float

    def __str__(self) -> str:
        if self.separated:
            return (
                f"separated: answerable ≤ {self.worst_answerable:.3f}, "
                f"unanswerable ≥ {self.best_unanswerable:.3f}, "
                f"margin {self.margin:.3f} → floor {self.floor:.3f}"
            )
        return (
            f"OVERLAPPING by {abs(self.margin):.3f}: answerable reaches "
            f"{self.worst_answerable:.3f} while unanswerable reaches "
            f"{self.best_unanswerable:.3f} — no threshold separates them"
        )


class RelevanceGate:
    """Answer "did this query find anything the corpus actually covers?".

    Works on plain numbers so it fits whatever your retriever returns — a list of
    distances, a list of ``(Document, score)`` pairs with a ``key``, or your own
    result objects.

    Args:
        floor: The threshold. A score on the *relevant* side of it passes.
        lower_is_better: ``True`` for distances (cosine distance, L2), ``False``
            for similarities (cosine similarity, ``ts_rank_cd``). Getting this
            backwards inverts the gate silently, which is why it has no default
            that suits both.

    Example::

        gate = RelevanceGate(floor=0.60)          # cosine distance
        hits = store.search_semantic(embedding, top_k=20)
        if not gate.is_answerable(hits, key=lambda h: h[1]):
            return "Nothing in the library covers this."

    Calibrating against labelled queries::

        reading = RelevanceGate.calibrate(real_scores, nonsense_scores)
        print(reading)              # says plainly when there is no gap
        gate = RelevanceGate(floor=reading.floor) if reading.separated else None
    """

    def __init__(self, floor: float, *, lower_is_better: bool = True) -> None:
        self.floor = float(floor)
        self.lower_is_better = lower_is_better

    # ── Public API ────────────────────────────────────────────────

    def best(
        self, results: Iterable[Any], *, key: Callable[[Any], float | None] | None = None
    ) -> float | None:
        """The closest score among *results*, or ``None`` when there is nothing to judge.

        ``None`` means "no opinion" — an empty result set, or scores that are all
        missing because nothing was searched by vector. It does **not** mean
        "irrelevant", and a caller that conflates the two turns a keyword-only
        search into a permanent "no material matches this request".
        """
        scores = [
            float(s)
            for s in ((key(r) if key else r) for r in results)
            if s is not None
        ]
        if not scores:
            return None
        return min(scores) if self.lower_is_better else max(scores)

    def passes(self, score: float | None) -> bool:
        """Whether one score is on the relevant side of the floor. ``None`` passes."""
        if score is None:
            return True
        return score <= self.floor if self.lower_is_better else score >= self.floor

    def is_answerable(
        self, results: Iterable[Any], *, key: Callable[[Any], float | None] | None = None
    ) -> bool:
        """Whether *results* contain anything the corpus genuinely covers.

        Empty results are never answerable. Beyond that the count is ignored
        entirely and only the best score is consulted, because the count is what
        lies.
        """
        materialised = list(results)
        if not materialised:
            return False
        return self.passes(self.best(materialised, key=key))

    def filter(
        self, results: Iterable[Any], *, key: Callable[[Any], float | None] | None = None
    ) -> list[Any]:
        """Drop individual results that fall outside the floor, keeping order.

        Use this to trim a candidate pool. Do **not** use it to decide whether the
        corpus answered at all — that is :meth:`is_answerable`, and a trimmed list
        that happens to be non-empty is not the same question.
        """
        return [
            r
            for r in results
            if self.passes(
                (lambda s: float(s) if s is not None else None)(key(r) if key else r)
            )
        ]

    # ── Calibration ───────────────────────────────────────────────

    @staticmethod
    def calibrate(
        answerable: Sequence[float],
        unanswerable: Sequence[float],
        *,
        lower_is_better: bool = True,
    ) -> Calibration:
        """Read a floor off two labelled populations of best-match scores.

        Feed it the best score for each of a set of queries the corpus *does*
        answer, and for a set it does not. Include ordinary, well-formed questions
        about the wrong subject among the latter, not only gibberish: gibberish is
        easy to separate and a sensible question about something the corpus has
        never heard of is what a user actually types.

        Raises:
            ValueError: if either population is empty. There is nothing to read.
        """
        if not answerable or not unanswerable:
            raise ValueError(
                "calibrate needs both populations; got "
                f"{len(answerable)} answerable and {len(unanswerable)} unanswerable"
            )
        if lower_is_better:
            worst_answerable = max(answerable)
            best_unanswerable = min(unanswerable)
            margin = best_unanswerable - worst_answerable
        else:
            worst_answerable = min(answerable)
            best_unanswerable = max(unanswerable)
            margin = worst_answerable - best_unanswerable

        separated = margin > 0
        floor = (worst_answerable + best_unanswerable) / 2 if separated else None
        return Calibration(
            floor=floor,
            separated=separated,
            worst_answerable=worst_answerable,
            best_unanswerable=best_unanswerable,
            margin=margin,
        )
