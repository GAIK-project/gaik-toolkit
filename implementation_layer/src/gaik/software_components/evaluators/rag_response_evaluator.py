"""RAGResponseEvaluator — referenced and pairwise judging of RAG outputs.

Two modes share one class:

- ``evaluate(df, ...)`` — score every candidate column against a reference
  column on a 4+1 dimensional rubric (coverage, contradiction, relevance,
  precision + holistic overall). Output: scored DataFrame + per-system aggregates.
- ``evaluate_pairwise(df, ...)`` — no reference. For every row, every C(N,2)
  pair of candidates is judged head-to-head on five intrinsic-quality aspects.
  Output: long-format ``comparisons_df`` + system ranking.

Both modes are provider-agnostic (any ``ProviderClient``) and ship with
overridable rubrics via ``ScoringSpec`` / ``PairwiseSpec``.
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

if TYPE_CHECKING:  # pragma: no cover
    import matplotlib.figure

    from gaik.software_components.llm.base import ProviderClient

logger = logging.getLogger(__name__)


# ============================================================================
# SCHEMAS — referenced mode
# ============================================================================


class CorrectnessScore(BaseModel):
    """4+1 dimensional scoring against a reference answer.

    Scratchpad fields force reasoning before any numeric score. Field order
    is intentional and must not be reordered.
    """

    omissions: str = Field(
        description=(
            "List every factual claim or nuance present in the reference that is absent "
            "from the RAG response. Quote or closely paraphrase the missing content. "
            "If nothing is missing, write 'None'."
        )
    )
    contradictions: str = Field(
        description=(
            "List every RAG claim that directly conflicts with an explicit statement in "
            "the reference. Name both the RAG claim and the reference statement it "
            "conflicts with. If there are no contradictions, write 'None'."
        )
    )
    relevance_notes: str = Field(
        description=(
            "Evaluate whether the RAG response addresses the user's actual question. "
            "Use ONLY the question and the RAG response — ignore the reference here. "
            "Note any aspects of the question that are ignored, deflected, or answered "
            "only tangentially. If the response fully addresses the question, write 'None'."
        )
    )
    precision_notes: str = Field(
        description=(
            "Identify claims in the RAG response stated with unnecessary vagueness, "
            "excessive hedging, or ambiguity on points where a clear answer is possible. "
            "Focus on cases where the vagueness would leave the user uncertain about "
            "something the reference treats as settled. If no such cases exist, write 'None'."
        )
    )
    coverage_score: Literal[0, 1, 2, 3] = Field(description="Coverage score 0-3 (see rubric)")
    contradiction_score: Literal[0, 1, 2] = Field(
        description="Contradiction score 0-2 (see rubric)"
    )
    relevance_score: Literal[0, 1, 2] = Field(description="Relevance score 0-2 (see rubric)")
    precision_score: Literal[0, 1, 2] = Field(description="Precision score 0-2 (see rubric)")
    overall_score: Literal[0, 1, 2, 3, 4] = Field(
        description=(
            "Holistic quality score 0-4. Assign this LAST, after completing all "
            "scratchpad fields and sub-scores. Not a formula — weight findings by "
            "their practical severity for this specific question. "
            "Hard constraints: relevance_score=0 → overall≤1; contradiction_score=0 → overall≤2."
        )
    )
    reason: str = Field(
        description=(
            "One or two sentences justifying the overall score, referencing the single "
            "most significant finding from the scratchpad fields above."
        )
    )


_COVERAGE_RUBRIC = """
COVERAGE (0-3) — how completely does the RAG response capture the informational content
of the reference?

  3 (Complete):    All core claims AND all materially important details from the reference
                   are present. The user would receive a functionally equivalent answer.

  2 (Mostly):      All core claims are present. At most one or two peripheral details or
                   minor nuances from the reference are absent. Nothing that changes the
                   practical answer is missing.

  1 (Partial):     The core answer is present, but at least one materially important detail
                   from the reference is missing — something a user would need to act
                   correctly or understand the topic fully.

  0 (Absent):      The core answer as established by the reference is not present. The user
                   would walk away without the essential information.

  Core vs. detail: if omitting a fact would change what the user does or decides, it is
  core. If omitting it leaves the practical answer intact but less complete, it is a detail.
"""

_CONTRADICTION_RUBRIC = """
CONTRADICTION (0-2) — does the RAG response make claims that conflict with the reference?

  2 (Clean):       Every claim in the RAG response is consistent with the reference.
                   Additional information not in the reference is neutral — you cannot
                   verify external facts, so do not penalize them.

  1 (Ambiguous):   No direct contradiction, but at least one statement is framed or worded
                   in a way that could mislead the user relative to the reference.

  0 (Contradicts): At least one RAG claim directly and explicitly conflicts with a specific
                   reference statement. The conflict must be clear and unambiguous — not
                   merely an omission or imprecise framing.

  A score of 1 or 0 requires you to name the specific statement in 'contradictions'.
"""

_RELEVANCE_RUBRIC = """
RELEVANCE (0-2) — does the RAG response address the user's actual question?
Evaluate this using ONLY the question and the RAG response. Ignore the reference entirely
for this dimension.

  2 (Addresses):   The response directly and substantively answers what the user asked.
  1 (Partial):     The response addresses a related topic but does not fully answer the
                   specific question asked.
  0 (Misses):      The response does not address the question.

  Hard constraint: relevance_score=0 → overall_score cannot exceed 1.
"""

_PRECISION_RUBRIC = """
PRECISION (0-2) — does the RAG response avoid vagueness that renders correct information
practically useless?

  2 (Precise):     Claims are specific and actionable. Where the reference gives a clear
                   rule, threshold, or condition, the RAG response states it clearly.
  1 (Somewhat vague): At least one claim is hedged or qualified beyond what the evidence
                   warrants, OR a clear rule from the reference is restated as uncertain.
  0 (Excessively vague): Pervasive hedging or ambiguity on points the reference treats
                   as settled.

  Do not penalize appropriate epistemic caution — only penalize vagueness that exceeds
  what the underlying content warrants.
"""

_OVERALL_RUBRIC = """
OVERALL SCORE (0-4) — holistic quality of the RAG response.

Assign this score AFTER completing all scratchpad fields and sub-scores.
This is not a formula. Weight findings by their practical severity for this question.

  4 (Excellent):   Complete, accurate, relevant, and precise.
  3 (Good):        Largely correct and relevant; minor omissions or imprecision only.
  2 (Fair):        Meaningful limitations but still provides value.
  1 (Poor):        Fails relevance, contradicts the reference, or has serious gaps.
  0 (Fails):       Irrelevant, contradicts core claims, or worthless.

Hard constraints (enforce strictly):
  - relevance_score = 0      →  overall_score cannot exceed 1
  - contradiction_score = 0  →  overall_score cannot exceed 2
"""

_REFERENCED_SYSTEM_PROMPT = f"""You are a precise, logical evaluator of RAG system responses.

Your task is to evaluate a RAG response on four independent dimensions, then synthesise an overall score.
Complete scratchpad fields (omissions, contradictions, relevance_notes, precision_notes)
before assigning any numeric score. Scores must follow from them logically.

{_COVERAGE_RUBRIC}
{_CONTRADICTION_RUBRIC}
{_RELEVANCE_RUBRIC}
{_PRECISION_RUBRIC}
{_OVERALL_RUBRIC}

GENERAL EVALUATION RULES:

1. COMPARISON SCOPE: You can only compare the RAG response against the reference answer and the
   user question. You have no access to the underlying source documents or knowledge base.

2. EXTRACT CLAIMS FROM THE REFERENCE: The reference may be raw statute text, informal notes,
   or a mix. Identify the factual claims it makes.

3. IGNORE FORMAT AND STRUCTURE: Section headers, sub-sections, and formatting are not evaluated.

4. IGNORE SOURCE FILE NAMES: Do not evaluate document names, file paths, or URLs.

5. MULTI-PART RESPONSES: A fact present in any sub-answer counts as covered.

6. EXTRA INFORMATION: Additional information not in the reference is neutral unless it
   directly contradicts an explicit reference statement.

7. REASONING ORDER: omissions → contradictions → relevance_notes → precision_notes,
   then sub-scores, then overall_score LAST.

Return a valid JSON object matching the required schema.
"""


@dataclass(frozen=True)
class ScoringSpec:
    """Overridable rubric + schema bundle for referenced-mode scoring."""

    schema: type[BaseModel]
    score_fields: dict[str, int]
    """{field_name_on_schema: max_value}. Defines score column order."""

    system_prompt: str
    overall_field: str = "overall_score"
    composite_weights: dict[str, float] | None = None
    """Weights for sub-dim normalised composite (excludes overall_field). Must sum to ~1."""

    reason_fields: tuple[str, ...] = ()
    """Scratchpad fields packed into the per-row reason text."""

    summary_reason_field: str = "reason"
    """Field used as the short justification."""


DEFAULT_SCORING_SPEC = ScoringSpec(
    schema=CorrectnessScore,
    score_fields={
        "coverage_score": 3,
        "contradiction_score": 2,
        "relevance_score": 2,
        "precision_score": 2,
        "overall_score": 4,
    },
    system_prompt=_REFERENCED_SYSTEM_PROMPT,
    overall_field="overall_score",
    composite_weights={
        "coverage_score": 0.45,
        "contradiction_score": 0.25,
        "relevance_score": 0.20,
        "precision_score": 0.10,
    },
    reason_fields=("omissions", "contradictions", "relevance_notes", "precision_notes"),
    summary_reason_field="reason",
)


# ============================================================================
# SCHEMAS — pairwise mode
# ============================================================================


_PAIRWISE_ASPECTS: tuple[str, ...] = (
    "directness",
    "specificity",
    "completeness",
    "consistency",
    "clarity",
)


class PairwiseVerdict(BaseModel):
    """Reference-free A-vs-B verdict with per-aspect Likert scores per side.

    Scratchpad first, aspect scores second, winner last. Order must not change.
    """

    a_summary: str = Field(description="One-sentence characterization of response A.")
    b_summary: str = Field(description="One-sentence characterization of response B.")
    key_differences: str = Field(
        description="What materially distinguishes A from B. Quote or paraphrase."
    )

    directness_a: Literal[1, 2, 3, 4, 5] = Field(description="A: directly answers the question?")
    directness_b: Literal[1, 2, 3, 4, 5] = Field(description="B: directly answers the question?")
    specificity_a: Literal[1, 2, 3, 4, 5] = Field(description="A: concrete vs vague claims")
    specificity_b: Literal[1, 2, 3, 4, 5] = Field(description="B: concrete vs vague claims")
    completeness_a: Literal[1, 2, 3, 4, 5] = Field(description="A: covers the question's scope")
    completeness_b: Literal[1, 2, 3, 4, 5] = Field(description="B: covers the question's scope")
    consistency_a: Literal[1, 2, 3, 4, 5] = Field(description="A: internal self-consistency")
    consistency_b: Literal[1, 2, 3, 4, 5] = Field(description="B: internal self-consistency")
    clarity_a: Literal[1, 2, 3, 4, 5] = Field(description="A: well-organized and unambiguous")
    clarity_b: Literal[1, 2, 3, 4, 5] = Field(description="B: well-organized and unambiguous")

    winner: Literal["A", "B", "tie"] = Field(
        description="Overall winner. Assign LAST, after all aspect scores."
    )
    confidence: Literal["low", "medium", "high"] = Field(
        description="How confident you are in the winner verdict."
    )
    reason: str = Field(
        description="One or two sentences citing the decisive aspect for the winner."
    )


_PAIRWISE_SYSTEM_PROMPT = """You compare two RAG responses ("A" and "B") to the SAME user question.

No reference answer is available. Judge intrinsic quality only — do not penalize either
side for facts you cannot verify externally. Ties are encouraged when responses are
roughly equivalent in quality.

For each of the five aspects below, score A and B INDEPENDENTLY on a 1-5 Likert scale.
Score every aspect before assigning the winner.

ASPECTS:

  Directness (1-5)   — Does the response answer the actual question asked, or does it
                        deflect, generalize, or answer a different question?
                        5 = directly answers; 1 = does not address the question.

  Specificity (1-5)  — Are claims concrete (numbers, conditions, named rules) or vague
                        (excessive hedging, ambiguity on settled points)?
                        5 = specific and actionable; 1 = pervasively vague.

  Completeness (1-5) — Does it cover the question's scope without leaving obvious gaps?
                        5 = covers all aspects implied by the question;
                        1 = major aspects ignored.

  Consistency (1-5)  — Does the response contradict itself anywhere?
                        5 = fully consistent; 1 = obvious internal contradictions.

  Clarity (1-5)      — Is it well-organized, readable, unambiguous?
                        5 = clear and easy to follow; 1 = confusing or poorly structured.

DECISION RULES:

  1. Complete a_summary, b_summary, key_differences BEFORE scoring.
  2. Score each aspect independently for A and B — do not anchor B on A.
  3. After all 10 aspect scores are committed, choose winner ∈ {"A", "B", "tie"}.
     - "tie" is the right answer when aspect scores roughly balance out.
     - The winner should reflect the totality of aspect scores, weighted by what
       matters most for this specific question.
  4. Set confidence:
       - "high"   if differences are clear across multiple aspects
       - "medium" if one aspect decides it
       - "low"    if it's close — prefer "tie" in this case
  5. IGNORE FORMAT: section headers, length differences, and source citations are not
     evaluated; only informational quality.

Return a valid JSON object matching the required schema.
"""


@dataclass(frozen=True)
class PairwiseSpec:
    """Overridable rubric + schema bundle for pairwise-mode judging."""

    schema: type[BaseModel]
    aspect_fields: tuple[str, ...]
    """Aspect names. For each, the schema must expose '{aspect}_a' and '{aspect}_b'."""

    aspect_max: int
    """Likert maximum (e.g. 5)."""

    system_prompt: str
    winner_field: str = "winner"
    confidence_field: str = "confidence"
    reason_field: str = "reason"
    summary_fields: tuple[str, ...] = ()
    """Scratchpad fields packed into the per-row reason text."""


DEFAULT_PAIRWISE_SPEC = PairwiseSpec(
    schema=PairwiseVerdict,
    aspect_fields=_PAIRWISE_ASPECTS,
    aspect_max=5,
    system_prompt=_PAIRWISE_SYSTEM_PROMPT,
    summary_fields=("a_summary", "b_summary", "key_differences"),
)


# ============================================================================
# RESULT DATACLASSES
# ============================================================================


@dataclass
class RAGResponseAggregate:
    """Per-system summary for referenced-mode evaluation."""

    system: str
    n: int
    means: dict[str, float]
    norms: dict[str, float]
    composite: float
    divergence: float
    constraint_violations: int


@dataclass
class RAGResponseEvalResult:
    """Full referenced-mode result."""

    scored_df: pd.DataFrame
    per_system: list[RAGResponseAggregate]
    spec: ScoringSpec
    cost_usd: float = 0.0
    duration_s: float = 0.0


@dataclass
class PairwiseComparison:
    """One head-to-head comparison row (post-aggregation across swap passes)."""

    question: str
    system_a: str
    system_b: str
    winner: Literal["A", "B", "tie"]
    confidence: str
    swap_consistent: bool
    aspect_scores_a: dict[str, float]
    aspect_scores_b: dict[str, float]
    reason: str


@dataclass
class PairwiseRanking:
    """One system's aggregated standing across all pairwise comparisons."""

    system: str
    wins: int
    losses: int
    ties: int
    win_rate: float
    avg_score: float
    aspect_means: dict[str, float]
    rank: int


@dataclass
class RAGPairwiseEvalResult:
    """Full pairwise-mode result."""

    comparisons_df: pd.DataFrame
    ranking: list[PairwiseRanking]
    spec: PairwiseSpec
    cost_usd: float = 0.0
    duration_s: float = 0.0


@dataclass
class ProgressEvent:
    """Emitted by ``on_progress`` callback (one event per LLM call completed)."""

    mode: Literal["referenced", "pairwise"]
    done: int
    total: int
    elapsed_s: float
    detail: dict[str, Any] = field(default_factory=dict)


# ============================================================================
# PLOTTING
# ============================================================================


def referenced_plots(
    result: RAGResponseEvalResult,
) -> dict[str, matplotlib.figure.Figure]:
    figs: dict[str, matplotlib.figure.Figure] = {}
    figs["score_distributions"] = _score_distributions(result)
    figs["per_system_means"] = _per_system_means(result)
    figs["calibration_scatter"] = _calibration_scatter(result)
    if any(a.constraint_violations for a in result.per_system):
        figs["constraint_violation_summary"] = _constraint_violation_summary(result)
    return figs


def _score_distributions(result: RAGResponseEvalResult):
    import matplotlib.pyplot as plt

    spec = result.spec
    systems = [a.system for a in result.per_system]
    dims = list(spec.score_fields.keys())
    n_sys, n_dim = len(systems), len(dims)
    fig, axes = plt.subplots(n_sys, n_dim, figsize=(2.6 * n_dim, 2.2 * n_sys), squeeze=False)
    for r, system in enumerate(systems):
        for c, dim in enumerate(dims):
            ax = axes[r][c]
            col = f"{system}_{dim}"
            vals = result.scored_df[col].dropna().astype(int)
            max_val = spec.score_fields[dim]
            bins = np.arange(-0.5, max_val + 1.5, 1)
            ax.hist(vals, bins=bins, color="#4C72B0", edgecolor="white")
            ax.set_xticks(range(0, max_val + 1))
            ax.set_xlim(-0.5, max_val + 0.5)
            if r == 0:
                ax.set_title(dim.replace("_score", ""), fontsize=9)
            if c == 0:
                ax.set_ylabel(system, fontsize=8)
            ax.tick_params(labelsize=7)
    fig.suptitle("Score distributions", fontsize=11)
    fig.tight_layout()
    return fig


def _per_system_means(result: RAGResponseEvalResult):
    import matplotlib.pyplot as plt

    spec = result.spec
    systems = [a.system for a in result.per_system]
    dims = list(spec.score_fields.keys())
    data = np.array([[a.norms.get(d, math.nan) for d in dims] for a in result.per_system])
    x = np.arange(len(dims))
    width = max(0.8 / max(len(systems), 1), 0.12)
    fig, ax = plt.subplots(figsize=(1.4 * len(dims) + 2, 4))
    for i, system in enumerate(systems):
        offset = (i - (len(systems) - 1) / 2) * width
        ax.bar(x + offset, data[i], width, label=system)
    ax.set_xticks(x)
    ax.set_xticklabels([d.replace("_score", "") for d in dims], rotation=20)
    ax.set_ylabel("Normalised mean (0-1)")
    ax.set_ylim(0, 1.05)
    ax.set_title("Per-system normalised means")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    return fig


def _calibration_scatter(result: RAGResponseEvalResult):
    import matplotlib.pyplot as plt

    spec = result.spec
    systems = [a.system for a in result.per_system]
    n = len(systems)
    cols = min(n, 3)
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(3.2 * cols, 3.2 * rows), squeeze=False)
    overall_max = spec.score_fields.get(spec.overall_field, 1)
    for i, system in enumerate(systems):
        ax = axes[i // cols][i % cols]
        sub = result.scored_df.dropna(subset=[f"{system}_{spec.overall_field}"])
        overall_norm = sub[f"{system}_{spec.overall_field}"].astype(float) / overall_max
        composite = sum(
            (sub[f"{system}_{k}"].astype(float) / spec.score_fields[k]) * w
            for k, w in (spec.composite_weights or {}).items()
        )
        ax.scatter(composite, overall_norm, alpha=0.6, s=20, color="#55A868")
        ax.plot([0, 1], [0, 1], "k--", linewidth=0.8, alpha=0.5)
        ax.set_xlim(0, 1.02)
        ax.set_ylim(0, 1.02)
        ax.set_xlabel("Mechanical composite", fontsize=8)
        ax.set_ylabel("Judge overall (norm.)", fontsize=8)
        ax.set_title(system, fontsize=9)
        ax.tick_params(labelsize=7)
    for j in range(n, rows * cols):
        axes[j // cols][j % cols].set_visible(False)
    fig.suptitle("Judge-overall vs. mechanical composite", fontsize=11)
    fig.tight_layout()
    return fig


def _constraint_violation_summary(result: RAGResponseEvalResult):
    import matplotlib.pyplot as plt

    systems = [a.system for a in result.per_system]
    counts = [a.constraint_violations for a in result.per_system]
    fig, ax = plt.subplots(figsize=(0.9 * len(systems) + 2, 3))
    ax.bar(systems, counts, color="#C44E52")
    ax.set_ylabel("Hard-constraint violations")
    ax.set_title("Constraint violations per system")
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    fig.tight_layout()
    return fig


def pairwise_plots(
    result: RAGPairwiseEvalResult,
) -> dict[str, matplotlib.figure.Figure]:
    return {
        "pairwise_win_matrix": _pairwise_win_matrix(result),
        "pairwise_ranking": _pairwise_ranking(result),
        "pairwise_aspect_radar": _pairwise_aspect_radar(result),
    }


def _pairwise_win_matrix(result: RAGPairwiseEvalResult):
    import matplotlib.pyplot as plt

    systems = sorted({r.system for r in result.ranking})
    idx = {s: i for i, s in enumerate(systems)}
    n = len(systems)
    matrix = np.full((n, n), np.nan)
    counts = np.zeros((n, n), dtype=int)
    wins = np.zeros((n, n), dtype=int)

    for _, row in result.comparisons_df.dropna(subset=["winner"]).iterrows():
        i, j = idx[row["system_a"]], idx[row["system_b"]]
        counts[i, j] += 1
        counts[j, i] += 1
        if row["winner"] == "A":
            wins[i, j] += 1
        elif row["winner"] == "B":
            wins[j, i] += 1

    for i in range(n):
        for j in range(n):
            if i != j and counts[i, j] > 0:
                matrix[i, j] = wins[i, j] / counts[i, j]

    fig, ax = plt.subplots(figsize=(0.7 * n + 2.5, 0.7 * n + 2))
    im = ax.imshow(matrix, cmap="RdYlGn", vmin=0, vmax=1, aspect="equal")
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(systems, rotation=30, ha="right")
    ax.set_yticklabels(systems)
    ax.set_xlabel("System B")
    ax.set_ylabel("System A")
    for i in range(n):
        for j in range(n):
            if not np.isnan(matrix[i, j]):
                ax.text(
                    j, i, f"{matrix[i, j]:.2f}", ha="center", va="center", color="black", fontsize=8
                )
    ax.set_title("Pairwise win rate: row A vs col B")
    fig.colorbar(im, ax=ax, shrink=0.7, label="P(A wins)")
    fig.tight_layout()
    return fig


def _pairwise_ranking(result: RAGPairwiseEvalResult):
    import matplotlib.pyplot as plt

    ranked = sorted(result.ranking, key=lambda r: r.rank)
    systems = [r.system for r in ranked]
    wrs = np.array([r.win_rate if not math.isnan(r.win_rate) else 0.0 for r in ranked])
    ns = np.array([r.wins + r.losses for r in ranked])
    lo, hi = _wilson_ci(wrs, ns)
    yerr = np.vstack([wrs - lo, hi - wrs])
    fig, ax = plt.subplots(figsize=(6, 0.5 * len(systems) + 1.5))
    y = np.arange(len(systems))
    ax.barh(y, wrs, xerr=yerr, color="#4C72B0", capsize=4)
    ax.set_yticks(y)
    ax.set_yticklabels(systems)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.0)
    ax.set_xlabel("Win rate (95% Wilson CI; ties excluded)")
    ax.set_title("Pairwise ranking")
    fig.tight_layout()
    return fig


def _pairwise_aspect_radar(result: RAGPairwiseEvalResult):
    import matplotlib.pyplot as plt

    spec = result.spec
    aspects = list(spec.aspect_fields)
    if not aspects:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, "No aspects defined", ha="center")
        return fig

    angles = np.linspace(0, 2 * np.pi, len(aspects), endpoint=False).tolist()
    angles += angles[:1]
    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw={"projection": "polar"})
    for r in sorted(result.ranking, key=lambda r: r.rank):
        vals = [r.aspect_means.get(a, 0.0) / spec.aspect_max for a in aspects]
        vals += vals[:1]
        ax.plot(angles, vals, label=r.system, linewidth=1.5)
        ax.fill(angles, vals, alpha=0.10)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(aspects, fontsize=9)
    ax.set_ylim(0, 1.0)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0.25", "0.50", "0.75", "1.00"], fontsize=7)
    ax.set_title("Pairwise aspect means (normalised)", pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.10), fontsize=8)
    fig.tight_layout()
    return fig


def _wilson_ci(p: np.ndarray, n: np.ndarray, z: float = 1.96) -> tuple[np.ndarray, np.ndarray]:
    """Wilson score interval. Returns (lower, upper) clipped to [0,1]."""
    safe_n = np.where(n > 0, n, 1)
    denom = 1 + z**2 / safe_n
    centre = (p + z**2 / (2 * safe_n)) / denom
    margin = z * np.sqrt(p * (1 - p) / safe_n + z**2 / (4 * safe_n**2)) / denom
    lo = np.clip(centre - margin, 0, 1)
    hi = np.clip(centre + margin, 0, 1)
    lo = np.where(n > 0, lo, p)
    hi = np.where(n > 0, hi, p)
    return lo, hi


# ============================================================================
# EVALUATOR
# ============================================================================


MIN_RESPONSE_CHARS = 20


class RAGResponseEvaluator:
    """LLM-judged scoring of RAG responses — referenced and pairwise modes."""

    def __init__(
        self,
        client: ProviderClient | None = None,
        *,
        scoring_spec: ScoringSpec | None = None,
        pairwise_spec: PairwiseSpec | None = None,
        max_concurrency: int = 5,
        retry_count: int = 3,
        retry_backoff_base: float = 2.0,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        if retry_count < 1:
            raise ValueError("retry_count must be >= 1")
        self._client = client
        self.scoring_spec = scoring_spec or DEFAULT_SCORING_SPEC
        self.pairwise_spec = pairwise_spec or DEFAULT_PAIRWISE_SPEC
        self.max_concurrency = max_concurrency
        self.retry_count = retry_count
        self.retry_backoff_base = retry_backoff_base

    @property
    def client(self) -> ProviderClient:
        if self._client is None:
            from gaik.software_components.llm import create_llm_client, get_llm_config

            self._client = create_llm_client(get_llm_config())
        return self._client

    # ------------------------------------------------------------------ judging

    def _judge_once(
        self,
        messages: list[dict],
        response_format: type[BaseModel],
    ) -> BaseModel:
        last_error: Exception | None = None
        for attempt in range(self.retry_count):
            try:
                return self.client.chat_parsed(
                    messages=messages,
                    response_format=response_format,
                    temperature=0,
                )
            except Exception as e:
                last_error = e
                logger.warning("Judge attempt %d/%d failed: %s", attempt + 1, self.retry_count, e)
                if attempt < self.retry_count - 1:
                    time.sleep(self.retry_backoff_base**attempt)
        raise RuntimeError(
            f"Judge failed after {self.retry_count} attempts: {last_error}"
        ) from last_error

    async def _judge_once_async(
        self,
        messages: list[dict],
        response_format: type[BaseModel],
        semaphore: asyncio.Semaphore,
    ) -> BaseModel:
        last_error: Exception | None = None
        for attempt in range(self.retry_count):
            try:
                async with semaphore:
                    return await asyncio.to_thread(
                        self.client.chat_parsed,
                        messages=messages,
                        response_format=response_format,
                        temperature=0,
                    )
            except Exception as e:
                last_error = e
                logger.warning("Judge attempt %d/%d failed: %s", attempt + 1, self.retry_count, e)
                if attempt < self.retry_count - 1:
                    await asyncio.sleep(self.retry_backoff_base**attempt)
        raise RuntimeError(
            f"Judge failed after {self.retry_count} attempts: {last_error}"
        ) from last_error

    # ============================================================== REFERENCED

    def evaluate(
        self,
        df: pd.DataFrame,
        *,
        question_col: str = "question",
        reference_col: str = "reference",
        candidate_cols: list[str] | None = None,
        resume_from: pd.DataFrame | None = None,
        on_progress: Callable[[ProgressEvent], None] | None = None,
    ) -> RAGResponseEvalResult:
        """Score each candidate column against the reference column."""
        spec = self.scoring_spec
        if candidate_cols is None:
            candidate_cols = [c for c in df.columns if c.endswith("_response")]
        if not candidate_cols:
            raise ValueError("No candidate columns supplied and no '*_response' columns found.")
        for col in (question_col, reference_col, *candidate_cols):
            if col not in df.columns:
                raise ValueError(f"Column '{col}' missing from DataFrame")

        _validate_referenced(df, question_col, reference_col, candidate_cols)

        scored_df = _init_scored_df(df, candidate_cols, list(spec.score_fields), resume_from)

        sentinel_field = next(iter(spec.score_fields))
        pending: list[tuple[str, int]] = [
            (col, idx)
            for col in candidate_cols
            for idx in scored_df.index[scored_df[f"{col}_{sentinel_field}"].isna()]
        ]
        total = len(pending)
        t0 = time.time()

        if total == 0:
            aggregates = [_aggregate_referenced(scored_df, col, spec) for col in candidate_cols]
            return RAGResponseEvalResult(scored_df=scored_df, per_system=aggregates, spec=spec)

        if self.max_concurrency == 1:
            for i, (col, idx) in enumerate(pending):
                verdict = self._judge_once(
                    _referenced_messages(
                        spec.system_prompt,
                        df.at[idx, question_col],
                        df.at[idx, col],
                        df.at[idx, reference_col],
                    ),
                    spec.schema,
                )
                _write_referenced_row(scored_df, idx, col, verdict, spec)
                _emit(on_progress, "referenced", i + 1, total, t0, col=col, row=idx)
        else:
            asyncio.run(
                self._evaluate_referenced_async(
                    df,
                    scored_df,
                    pending,
                    question_col,
                    reference_col,
                    total,
                    t0,
                    on_progress,
                )
            )

        aggregates = [_aggregate_referenced(scored_df, col, spec) for col in candidate_cols]
        return RAGResponseEvalResult(
            scored_df=scored_df,
            per_system=aggregates,
            spec=spec,
            duration_s=time.time() - t0,
        )

    async def _evaluate_referenced_async(
        self,
        df: pd.DataFrame,
        scored_df: pd.DataFrame,
        pending: list[tuple[str, int]],
        question_col: str,
        reference_col: str,
        total: int,
        t0: float,
        on_progress: Callable[[ProgressEvent], None] | None,
    ) -> None:
        spec = self.scoring_spec
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def _one(col: str, idx: int) -> tuple[str, int, BaseModel]:
            verdict = await self._judge_once_async(
                _referenced_messages(
                    spec.system_prompt,
                    df.at[idx, question_col],
                    df.at[idx, col],
                    df.at[idx, reference_col],
                ),
                spec.schema,
                semaphore,
            )
            return col, idx, verdict

        done = 0
        for coro in asyncio.as_completed([_one(col, idx) for col, idx in pending]):
            col, idx, verdict = await coro
            _write_referenced_row(scored_df, idx, col, verdict, spec)
            done += 1
            _emit(on_progress, "referenced", done, total, t0, col=col, row=idx)

    # ================================================================ PAIRWISE

    def evaluate_pairwise(
        self,
        df: pd.DataFrame,
        *,
        question_col: str = "question",
        candidate_cols: list[str] | None = None,
        swap_and_average: bool = True,
        resume_from: pd.DataFrame | None = None,
        on_progress: Callable[[ProgressEvent], None] | None = None,
        random_seed: int | None = None,
    ) -> RAGPairwiseEvalResult:
        """Reference-free pairwise judging across N candidate columns.

        For each row, judge every C(N,2) pair. Each LLM call internally
        randomizes which side is presented as "A" vs "B" (mapped back before
        storage). When ``swap_and_average=True``, two passes (original and
        swapped) are run; their aspect scores are averaged and the winner is
        ``"tie"`` unless both passes agree.
        """
        spec = self.pairwise_spec
        if candidate_cols is None:
            candidate_cols = [c for c in df.columns if c.endswith("_response")]
        if len(candidate_cols) < 2:
            raise ValueError("Pairwise mode requires at least 2 candidate columns")
        if question_col not in df.columns:
            raise ValueError(f"Column '{question_col}' missing from DataFrame")
        for col in candidate_cols:
            if col not in df.columns:
                raise ValueError(f"Column '{col}' missing from DataFrame")

        _validate_pairwise(df, question_col, candidate_cols)

        pairs: list[tuple[str, str]] = [
            (candidate_cols[i], candidate_cols[j])
            for i in range(len(candidate_cols))
            for j in range(i + 1, len(candidate_cols))
        ]

        comp_df = _init_pairwise_df(df, question_col, pairs, spec, resume_from)
        pending = comp_df.index[comp_df["winner"].isna()].tolist()
        total = len(pending)
        t0 = time.time()
        rng = random.Random(random_seed)

        if total > 0:
            if self.max_concurrency == 1:
                for i, idx in enumerate(pending):
                    outcome = self._judge_pair(
                        comp_df.at[idx, "question"],
                        comp_df.at[idx, "_resp_a"],
                        comp_df.at[idx, "_resp_b"],
                        swap_and_average,
                        rng,
                    )
                    _write_pairwise_row(comp_df, idx, outcome, spec)
                    _emit(on_progress, "pairwise", i + 1, total, t0, row=idx)
            else:
                asyncio.run(
                    self._evaluate_pairwise_async(
                        comp_df,
                        pending,
                        swap_and_average,
                        rng,
                        total,
                        t0,
                        on_progress,
                    )
                )

        comp_df_out = comp_df.drop(columns=["_resp_a", "_resp_b"])
        ranking = _aggregate_pairwise(comp_df_out, candidate_cols, spec)
        return RAGPairwiseEvalResult(
            comparisons_df=comp_df_out,
            ranking=ranking,
            spec=spec,
            duration_s=time.time() - t0,
        )

    async def _evaluate_pairwise_async(
        self,
        comp_df: pd.DataFrame,
        pending: list[int],
        swap_and_average: bool,
        rng: random.Random,
        total: int,
        t0: float,
        on_progress: Callable[[ProgressEvent], None] | None,
    ) -> None:
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def _one(idx: int) -> tuple[int, _PairOutcome]:
            outcome = await self._judge_pair_async(
                comp_df.at[idx, "question"],
                comp_df.at[idx, "_resp_a"],
                comp_df.at[idx, "_resp_b"],
                swap_and_average,
                rng,
                semaphore,
            )
            return idx, outcome

        done = 0
        for coro in asyncio.as_completed([_one(idx) for idx in pending]):
            idx, outcome = await coro
            _write_pairwise_row(comp_df, idx, outcome, self.pairwise_spec)
            done += 1
            _emit(on_progress, "pairwise", done, total, t0, row=idx)

    def _judge_pair(
        self,
        question: str,
        resp_a: str,
        resp_b: str,
        swap_and_average: bool,
        rng: random.Random,
    ) -> _PairOutcome:
        spec = self.pairwise_spec
        flip_first = rng.random() < 0.5
        first_a, first_b = (resp_b, resp_a) if flip_first else (resp_a, resp_b)
        v1 = self._judge_once(
            _pairwise_messages(spec.system_prompt, question, first_a, first_b),
            spec.schema,
        )
        v1_canon = _canonicalize_verdict(v1, spec, flipped=flip_first)
        if not swap_and_average:
            return _build_outcome(v1_canon, None, spec)
        v2 = self._judge_once(
            _pairwise_messages(spec.system_prompt, question, resp_b, resp_a),
            spec.schema,
        )
        v2_canon = _canonicalize_verdict(v2, spec, flipped=True)
        return _build_outcome(v1_canon, v2_canon, spec)

    async def _judge_pair_async(
        self,
        question: str,
        resp_a: str,
        resp_b: str,
        swap_and_average: bool,
        rng: random.Random,
        semaphore: asyncio.Semaphore,
    ) -> _PairOutcome:
        spec = self.pairwise_spec
        flip_first = rng.random() < 0.5
        first_a, first_b = (resp_b, resp_a) if flip_first else (resp_a, resp_b)
        v1 = await self._judge_once_async(
            _pairwise_messages(spec.system_prompt, question, first_a, first_b),
            spec.schema,
            semaphore,
        )
        v1_canon = _canonicalize_verdict(v1, spec, flipped=flip_first)
        if not swap_and_average:
            return _build_outcome(v1_canon, None, spec)
        v2 = await self._judge_once_async(
            _pairwise_messages(spec.system_prompt, question, resp_b, resp_a),
            spec.schema,
            semaphore,
        )
        v2_canon = _canonicalize_verdict(v2, spec, flipped=True)
        return _build_outcome(v1_canon, v2_canon, spec)

    # ----------------------------------------------------------------- saving

    def save(
        self,
        result: RAGResponseEvalResult | RAGPairwiseEvalResult,
        output_dir: str | Path,
        *,
        write_plots: bool = True,
        plot_formats: tuple[str, ...] = ("png",),
    ) -> None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        if isinstance(result, RAGResponseEvalResult):
            result.scored_df.to_csv(out / "rag_eval_scored.csv", index=False)
            _summary_referenced_csv(result).to_csv(out / "rag_eval_summary.csv", index=False)
        else:
            result.comparisons_df.to_csv(out / "rag_eval_pairwise.csv", index=False)
            _summary_pairwise_csv(result).to_csv(out / "rag_eval_pairwise_ranking.csv", index=False)
        if write_plots:
            figs = self.plots(result)
            for name, fig in figs.items():
                for fmt in plot_formats:
                    fig.savefig(out / f"{name}.{fmt}", bbox_inches="tight", dpi=150)

    def plots(
        self,
        result: RAGResponseEvalResult | RAGPairwiseEvalResult,
    ) -> dict[str, matplotlib.figure.Figure]:
        if isinstance(result, RAGResponseEvalResult):
            return referenced_plots(result)
        return pairwise_plots(result)


# ============================================================================
# INTERNAL HELPERS
# ============================================================================


@dataclass
class _CanonVerdict:
    """Verdict mapped into the original (A,B) frame regardless of judge order."""

    winner: Literal["A", "B", "tie"]
    confidence: str
    aspect_a: dict[str, int]
    aspect_b: dict[str, int]
    reason: str
    summary_text: str


@dataclass
class _PairOutcome:
    winner: Literal["A", "B", "tie"]
    confidence: str
    swap_consistent: bool
    aspect_a: dict[str, float]
    aspect_b: dict[str, float]
    reason: str


def _referenced_messages(
    system_prompt: str, question: str, response: str, reference: str
) -> list[dict]:
    user = (
        f"User question:\n<question>\n{question}\n</question>\n\n"
        f"Reference answer:\n<reference_answer>\n{reference}\n</reference_answer>\n\n"
        f"RAG response to evaluate:\n<RAG_answer>\n{response}\n</RAG_answer>\n"
    )
    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": user}]


def _pairwise_messages(system_prompt: str, question: str, resp_a: str, resp_b: str) -> list[dict]:
    user = (
        f"User question:\n<question>\n{question}\n</question>\n\n"
        f"Response A:\n<response_a>\n{resp_a}\n</response_a>\n\n"
        f"Response B:\n<response_b>\n{resp_b}\n</response_b>\n"
    )
    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": user}]


def _canonicalize_verdict(
    verdict: BaseModel, spec: PairwiseSpec, *, flipped: bool
) -> _CanonVerdict:
    """Map judge output back to original (A,B) frame.

    When ``flipped`` is True the judge saw resp_b as "A" and resp_a as "B",
    so winner and aspect scores are swapped before returning.
    """
    aspect_first = {a: int(getattr(verdict, f"{a}_a")) for a in spec.aspect_fields}
    aspect_second = {a: int(getattr(verdict, f"{a}_b")) for a in spec.aspect_fields}
    winner = getattr(verdict, spec.winner_field)
    confidence = getattr(verdict, spec.confidence_field)
    reason = getattr(verdict, spec.reason_field)
    summary_text = " | ".join(f"[{f}] {getattr(verdict, f, '')}" for f in spec.summary_fields)
    if flipped:
        winner = {"A": "B", "B": "A", "tie": "tie"}[winner]
        aspect_a, aspect_b = aspect_second, aspect_first
    else:
        aspect_a, aspect_b = aspect_first, aspect_second
    return _CanonVerdict(
        winner=winner,
        confidence=confidence,
        aspect_a=aspect_a,
        aspect_b=aspect_b,
        reason=reason,
        summary_text=summary_text,
    )


def _build_outcome(v1: _CanonVerdict, v2: _CanonVerdict | None, spec: PairwiseSpec) -> _PairOutcome:
    if v2 is None:
        return _PairOutcome(
            winner=v1.winner,
            confidence=v1.confidence,
            swap_consistent=True,
            aspect_a={k: float(v) for k, v in v1.aspect_a.items()},
            aspect_b={k: float(v) for k, v in v1.aspect_b.items()},
            reason=f"{v1.summary_text} | [reason] {v1.reason}",
        )
    swap_consistent = v1.winner == v2.winner
    winner: Literal["A", "B", "tie"] = v1.winner if swap_consistent else "tie"
    aspect_a = {k: (v1.aspect_a[k] + v2.aspect_a[k]) / 2.0 for k in v1.aspect_a}
    aspect_b = {k: (v1.aspect_b[k] + v2.aspect_b[k]) / 2.0 for k in v1.aspect_b}
    reason = (
        f"{v1.summary_text} | [reason] {v1.reason}"
        if swap_consistent
        else f"Disagreement under swap: '{v1.reason}' vs '{v2.reason}'"
    )
    return _PairOutcome(
        winner=winner,
        confidence=v1.confidence if swap_consistent else "low",
        swap_consistent=swap_consistent,
        aspect_a=aspect_a,
        aspect_b=aspect_b,
        reason=reason,
    )


# --- validation -------------------------------------------------------------


def _validate_referenced(
    df: pd.DataFrame,
    question_col: str,
    reference_col: str,
    candidate_cols: list[str],
) -> None:
    if df[question_col].duplicated().any():
        dups = df.loc[df[question_col].duplicated(), question_col].head(3).tolist()
        raise ValueError(f"Duplicate questions: {dups}")
    if df[question_col].isna().any() or df[reference_col].isna().any():
        raise ValueError("Question or reference column contains NaN")
    bad = df[reference_col].astype(str).str.strip().eq("")
    if bad.any():
        raise ValueError(f"Empty/whitespace references at rows: {df.index[bad].tolist()}")
    for col in candidate_cols:
        if df[col].isna().any():
            raise ValueError(f"NaN in candidate column '{col}'")
        bad = df[col].astype(str).str.strip().eq("")
        if bad.any():
            raise ValueError(
                f"Empty/whitespace responses in '{col}' at rows: {df.index[bad].tolist()}"
            )
        short = df[col].astype(str).str.len() < MIN_RESPONSE_CHARS
        if short.any():
            logger.warning(
                "%s: %d response(s) shorter than %d chars",
                col,
                int(short.sum()),
                MIN_RESPONSE_CHARS,
            )


def _validate_pairwise(df: pd.DataFrame, question_col: str, candidate_cols: list[str]) -> None:
    if df[question_col].duplicated().any():
        dups = df.loc[df[question_col].duplicated(), question_col].head(3).tolist()
        raise ValueError(f"Duplicate questions: {dups}")
    if df[question_col].isna().any():
        raise ValueError("Question column contains NaN")
    for col in candidate_cols:
        if df[col].isna().any():
            raise ValueError(f"NaN in candidate column '{col}'")
        bad = df[col].astype(str).str.strip().eq("")
        if bad.any():
            raise ValueError(
                f"Empty/whitespace responses in '{col}' at rows: {df.index[bad].tolist()}"
            )


# --- referenced df management -----------------------------------------------


def _init_scored_df(
    df: pd.DataFrame,
    candidate_cols: list[str],
    score_fields: list[str],
    resume_from: pd.DataFrame | None,
) -> pd.DataFrame:
    scored = (
        resume_from.copy()
        if (resume_from is not None and len(resume_from) == len(df))
        else df.copy()
    )
    for col in candidate_cols:
        for field_name in score_fields:
            colname = f"{col}_{field_name}"
            if colname not in scored.columns:
                scored[colname] = pd.NA
        if f"{col}_reason" not in scored.columns:
            scored[f"{col}_reason"] = pd.NA
    return scored


def _write_referenced_row(
    scored_df: pd.DataFrame,
    idx: int,
    col: str,
    verdict: BaseModel,
    spec: ScoringSpec,
) -> None:
    for field_name in spec.score_fields:
        scored_df.at[idx, f"{col}_{field_name}"] = int(getattr(verdict, field_name))
    reason_parts = [f"[{f}] {getattr(verdict, f, '')}" for f in spec.reason_fields]
    reason_parts.append(
        f"[{spec.summary_reason_field}] {getattr(verdict, spec.summary_reason_field, '')}"
    )
    scored_df.at[idx, f"{col}_reason"] = " | ".join(reason_parts)


def _aggregate_referenced(
    scored_df: pd.DataFrame, col: str, spec: ScoringSpec
) -> RAGResponseAggregate:
    sentinel = f"{col}_{next(iter(spec.score_fields))}"
    sub = scored_df.loc[scored_df[sentinel].notna()]
    n = len(sub)
    means: dict[str, float] = {}
    norms: dict[str, float] = {}
    for field_name, max_val in spec.score_fields.items():
        vals = sub[f"{col}_{field_name}"].astype(float)
        means[field_name] = float(vals.mean()) if n else math.nan
        norms[field_name] = means[field_name] / max_val if n else math.nan

    composite = math.nan
    divergence = math.nan
    if spec.composite_weights and n:
        composite = sum(norms[k] * w for k, w in spec.composite_weights.items() if k in norms)
        if spec.overall_field in norms:
            comp_series = sum(
                (sub[f"{col}_{k}"].astype(float) / spec.score_fields[k]) * w
                for k, w in spec.composite_weights.items()
            )
            overall_series = (
                sub[f"{col}_{spec.overall_field}"].astype(float)
                / spec.score_fields[spec.overall_field]
            )
            divergence = float((overall_series - comp_series).abs().mean())

    return RAGResponseAggregate(
        system=col,
        n=n,
        means=means,
        norms=norms,
        composite=composite,
        divergence=divergence,
        constraint_violations=_count_constraint_violations(sub, col, spec),
    )


def _count_constraint_violations(sub: pd.DataFrame, col: str, spec: ScoringSpec) -> int:
    """Count rows where the judge violated hard overall-score constraints."""
    rel_col = f"{col}_relevance_score"
    con_col = f"{col}_contradiction_score"
    ov_col = f"{col}_{spec.overall_field}"
    if not all(c in sub.columns for c in (rel_col, con_col, ov_col)):
        return 0
    violations = 0
    for idx in sub.index[(sub[rel_col] == 0) & (sub[ov_col] > 1)]:
        violations += 1
        logger.warning(
            "Constraint violation [%s] row %s: relevance=0 but overall=%s",
            col,
            idx,
            sub.at[idx, ov_col],
        )
    for idx in sub.index[(sub[con_col] == 0) & (sub[ov_col] > 2)]:
        violations += 1
        logger.warning(
            "Constraint violation [%s] row %s: contradiction=0 but overall=%s",
            col,
            idx,
            sub.at[idx, ov_col],
        )
    return violations


def _summary_referenced_csv(result: RAGResponseEvalResult) -> pd.DataFrame:
    rows = []
    for agg in result.per_system:
        row = {
            "system": agg.system,
            "n": agg.n,
            "composite": agg.composite,
            "divergence": agg.divergence,
            "constraint_violations": agg.constraint_violations,
        }
        for k, v in agg.means.items():
            row[f"mean_{k}"] = v
        for k, v in agg.norms.items():
            row[f"norm_{k}"] = v
        rows.append(row)
    return pd.DataFrame(rows)


# --- pairwise df management -------------------------------------------------


def _init_pairwise_df(
    df: pd.DataFrame,
    question_col: str,
    pairs: list[tuple[str, str]],
    spec: PairwiseSpec,
    resume_from: pd.DataFrame | None,
) -> pd.DataFrame:
    """Build long-format dataframe with one row per (question, A, B) pair.

    Hidden ``_resp_a`` / ``_resp_b`` columns carry response text for judging
    and are stripped before the result is returned.
    """
    prior = None
    if resume_from is not None and {"question", "system_a", "system_b", "winner"} <= set(
        resume_from.columns
    ):
        prior = resume_from.set_index(["question", "system_a", "system_b"]).copy()

    base_cols = [
        "question",
        "system_a",
        "system_b",
        "winner",
        "confidence",
        "swap_consistent",
        "reason",
        "_resp_a",
        "_resp_b",
    ]
    aspect_cols = [f"{a}_a" for a in spec.aspect_fields] + [f"{a}_b" for a in spec.aspect_fields]

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        q = row[question_col]
        for a, b in pairs:
            entry: dict[str, Any] = {
                "question": q,
                "system_a": a,
                "system_b": b,
                "winner": pd.NA,
                "confidence": pd.NA,
                "swap_consistent": pd.NA,
                "reason": pd.NA,
                "_resp_a": row[a],
                "_resp_b": row[b],
                **{ac: pd.NA for ac in aspect_cols},
            }
            if prior is not None and (q, a, b) in prior.index:
                pr = prior.loc[(q, a, b)]
                if pd.notna(pr.get("winner", pd.NA)):
                    entry.update(
                        {
                            "winner": pr["winner"],
                            "confidence": pr.get("confidence", pd.NA),
                            "swap_consistent": pr.get("swap_consistent", pd.NA),
                            "reason": pr.get("reason", pd.NA),
                            **{ac: pr[ac] for ac in aspect_cols if ac in pr},
                        }
                    )
            rows.append(entry)
    return pd.DataFrame(rows, columns=base_cols + aspect_cols)


def _write_pairwise_row(
    comp_df: pd.DataFrame, idx: int, outcome: _PairOutcome, spec: PairwiseSpec
) -> None:
    comp_df.at[idx, "winner"] = outcome.winner
    comp_df.at[idx, "confidence"] = outcome.confidence
    comp_df.at[idx, "swap_consistent"] = bool(outcome.swap_consistent)
    comp_df.at[idx, "reason"] = outcome.reason
    for aspect in spec.aspect_fields:
        comp_df.at[idx, f"{aspect}_a"] = outcome.aspect_a[aspect]
        comp_df.at[idx, f"{aspect}_b"] = outcome.aspect_b[aspect]


def _aggregate_pairwise(
    comp_df: pd.DataFrame, candidate_cols: list[str], spec: PairwiseSpec
) -> list[PairwiseRanking]:
    """Pool wins/losses/ties + per-aspect means per system."""
    stats: dict[str, dict[str, Any]] = {
        s: {
            "wins": 0,
            "losses": 0,
            "ties": 0,
            "aspect_sums": {a: 0.0 for a in spec.aspect_fields},
            "aspect_counts": 0,
        }
        for s in candidate_cols
    }
    for _, row in comp_df[comp_df["winner"].notna()].iterrows():
        a, b, w = row["system_a"], row["system_b"], row["winner"]
        if w == "A":
            stats[a]["wins"] += 1
            stats[b]["losses"] += 1
        elif w == "B":
            stats[b]["wins"] += 1
            stats[a]["losses"] += 1
        else:
            stats[a]["ties"] += 1
            stats[b]["ties"] += 1
        for aspect in spec.aspect_fields:
            stats[a]["aspect_sums"][aspect] += float(row[f"{aspect}_a"])
            stats[b]["aspect_sums"][aspect] += float(row[f"{aspect}_b"])
        stats[a]["aspect_counts"] += 1
        stats[b]["aspect_counts"] += 1

    rankings: list[PairwiseRanking] = []
    for system, s in stats.items():
        decisive = s["wins"] + s["losses"]
        n_comp = decisive + s["ties"]
        win_rate = s["wins"] / decisive if decisive else math.nan
        avg_score = (s["wins"] - s["losses"]) / n_comp if n_comp else math.nan
        aspect_means = (
            {a: s["aspect_sums"][a] / s["aspect_counts"] for a in spec.aspect_fields}
            if s["aspect_counts"]
            else {a: math.nan for a in spec.aspect_fields}
        )
        rankings.append(
            PairwiseRanking(
                system=system,
                wins=s["wins"],
                losses=s["losses"],
                ties=s["ties"],
                win_rate=win_rate,
                avg_score=avg_score,
                aspect_means=aspect_means,
                rank=0,
            )
        )

    def _aspect_avg(r: PairwiseRanking) -> float:
        vals = [v for v in r.aspect_means.values() if not math.isnan(v)]
        return sum(vals) / len(vals) if vals else 0.0

    rankings.sort(
        key=lambda r: (
            -(r.win_rate if not math.isnan(r.win_rate) else -1),
            -_aspect_avg(r),
            -(r.avg_score if not math.isnan(r.avg_score) else -1),
        )
    )
    for i, r in enumerate(rankings):
        r.rank = i + 1
    return rankings


def _summary_pairwise_csv(result: RAGPairwiseEvalResult) -> pd.DataFrame:
    rows = []
    for r in result.ranking:
        row = {
            "rank": r.rank,
            "system": r.system,
            "wins": r.wins,
            "losses": r.losses,
            "ties": r.ties,
            "win_rate": r.win_rate,
            "avg_score": r.avg_score,
        }
        for k, v in r.aspect_means.items():
            row[f"mean_{k}"] = v
        rows.append(row)
    return pd.DataFrame(rows)


# --- progress ---------------------------------------------------------------


def _emit(
    cb: Callable[[ProgressEvent], None] | None,
    mode: Literal["referenced", "pairwise"],
    done: int,
    total: int,
    t0: float,
    **detail: Any,
) -> None:
    if cb:
        cb(
            ProgressEvent(
                mode=mode, done=done, total=total, elapsed_s=time.time() - t0, detail=detail
            )
        )
