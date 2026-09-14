"""GPT-4o chunk durations must stay inside the API's per-request duration limit."""

from __future__ import annotations

from pathlib import Path

import pytest

from gaik.software_components.parallel_transcriber.config import TranscriptionConfig
from gaik.software_components.parallel_transcriber.ffmpeg import compute_chunk_specs
from gaik.software_components.parallel_transcriber.pipeline import (
    _GPT4O_API_DURATION_LIMIT_SECONDS,
    _MAX_GPT4O_DURATION_SECONDS,
)


def _gpt4o_chunk_minutes(cfg: TranscriptionConfig) -> int:
    """Mirror of the cap the pipeline applies when picking GPT-4o chunk length."""
    budget_seconds = _GPT4O_API_DURATION_LIMIT_SECONDS - 2 * cfg.chunk_overlap_seconds
    return max(1, min(cfg.gpt4o_chunk_duration_minutes, int(budget_seconds // 60)))


def test_single_pass_ceiling_stays_under_the_api_limit():
    assert _MAX_GPT4O_DURATION_SECONDS < _GPT4O_API_DURATION_LIMIT_SECONDS


@pytest.mark.parametrize("overlap_seconds", [0.0, 15.0, 30.0, 60.0])
@pytest.mark.parametrize("total_duration", [2760.0, 4140.0, 7200.0, 21_600.0])
def test_no_chunk_exceeds_the_api_limit(
    tmp_path: Path, total_duration: float, overlap_seconds: float
):
    """Regression: a middle chunk carries the overlap on *both* sides.

    With the previous 23-minute chunk and a 15 s overlap that came to
    15 + 1380 + 15 = 1410 s per middle chunk, so every recording longer than
    ~46 min failed with
    ``audio duration ... is longer than 1400 seconds``.
    """
    cfg = TranscriptionConfig(chunk_overlap_seconds=overlap_seconds)

    specs = compute_chunk_specs(
        total_duration=total_duration,
        chunk_duration_minutes=_gpt4o_chunk_minutes(cfg),
        overlap_seconds=overlap_seconds,
        output_dir=tmp_path,
        file_stem="recording",
    )

    assert specs
    assert max(spec.duration for spec in specs) <= _GPT4O_API_DURATION_LIMIT_SECONDS
