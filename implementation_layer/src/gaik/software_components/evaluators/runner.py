"""Generic batch runner that ties a callable pipeline to an evaluator."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .dataset import EvaluationDataset, EvaluationItem

logger = logging.getLogger(__name__)


PipelineFn = Callable[[EvaluationItem], Any]
"""A pipeline takes an :class:`EvaluationItem` and returns whatever the
evaluator expects (extractor dict, RAG output dict, etc.)."""


@dataclass
class RunnerResult:
    """Outputs from one batch run."""

    outputs: list[Any]
    durations_s: list[float]
    total_duration_s: float
    n_failures: int = 0
    failures: list[tuple[int, BaseException]] = field(default_factory=list)

    def succeeded(self) -> list[Any]:
        """Outputs only for items that did not raise."""
        bad = {idx for idx, _ in self.failures}
        return [out for i, out in enumerate(self.outputs) if i not in bad]


class BatchEvaluationRunner:
    """Run a pipeline over an :class:`EvaluationDataset` and collect outputs.

    Args:
        pipeline: Any callable ``EvaluationItem -> Any``. Often a small
            wrapper around :class:`gaik.software_components.extractor.DataExtractor`
            or :class:`gaik.software_modules.RAG_workflow.RAGWorkflow.run`.
        on_error: ``"raise"`` (default) re-raises the first failure;
            ``"skip"`` records it in :class:`RunnerResult.failures` and
            keeps going.
    """

    def __init__(
        self,
        pipeline: PipelineFn,
        *,
        on_error: str = "raise",
    ) -> None:
        if on_error not in ("raise", "skip"):
            raise ValueError(f"on_error must be 'raise' or 'skip', got {on_error!r}")
        self.pipeline = pipeline
        self.on_error = on_error

    def run(self, dataset: EvaluationDataset) -> RunnerResult:
        outputs: list[Any] = []
        durations: list[float] = []
        failures: list[tuple[int, BaseException]] = []

        t_total = time.perf_counter()
        for idx, item in enumerate(dataset):
            t0 = time.perf_counter()
            try:
                out = self.pipeline(item)
            except BaseException as exc:
                if self.on_error == "raise":
                    raise
                logger.warning(
                    "Pipeline failed on item %d: %s", idx, exc, exc_info=True
                )
                failures.append((idx, exc))
                outputs.append(None)
            else:
                outputs.append(out)
            durations.append(time.perf_counter() - t0)

        return RunnerResult(
            outputs=outputs,
            durations_s=durations,
            total_duration_s=time.perf_counter() - t_total,
            n_failures=len(failures),
            failures=failures,
        )
