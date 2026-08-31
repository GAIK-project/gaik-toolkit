"""Ranking, fusion and reordering building block."""

from .ranker import Ranker, default_key, reciprocal_rank_fusion

__all__ = [
    "Ranker",
    "reciprocal_rank_fusion",
    "default_key",
]

__version__ = "0.1.0"
