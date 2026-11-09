"""Merging chunk transcripts, timestamps, WebVTT and the extraction temp folder."""

import glob
import os
import tempfile

import pytest
from gaik.software_components.parallel_transcriber import pipeline as pipeline_module
from gaik.software_components.parallel_transcriber.pipeline import ParallelTranscriber
from gaik.software_components.parallel_transcriber.srt import (
    combine_srt_chunks,
    parse_srt_content,
    seconds_to_time,
)

# Two 20-minute chunks with 15 s of overlap on each side of the boundary at 1200 s:
# the first covers 0-1215 s, the second 1185 s onwards.
META = [
    {"nominal_start": 0, "overlap_start": 0, "overlap_end": 15},
    {"nominal_start": 1200, "overlap_start": 15, "overlap_end": 0},
]


def _srt(*cues: tuple[float, float, str]) -> str:
    return "\n\n".join(
        f"{i}\n{seconds_to_time(start)} --> {seconds_to_time(end)}\n{text}"
        for i, (start, end, text) in enumerate(cues, start=1)
    )


def _merged(first: str, second: str, meta=META) -> list[tuple[float, str]]:
    cues = parse_srt_content(combine_srt_chunks([first, second], meta))
    return [(cue["start_seconds"], cue["text"]) for cue in cues]


def test_the_overlap_after_a_boundary_is_taken_from_the_later_chunk_only():
    # Both chunks transcribe 1200-1215 s, split into segments differently.
    first = _srt(
        (1190, 1195, "before the boundary"),
        (1198, 1203, "crosses the boundary"),
        (1205, 1210, "after one"),
        (1211, 1214, "after two"),
    )
    second = _srt(
        (5, 10, "before the boundary, again"),  # 1190-1195 s
        (13, 18, "crosses it too"),  # 1198-1203 s
        (20, 29, "after one and after two"),  # 1205-1214 s
        (100, 103, "much later"),  # 1285 s
    )

    assert _merged(first, second) == [
        (1190.0, "before the boundary"),
        (1198.0, "crosses the boundary"),
        (1200.0, "crosses it too"),
        (1205.0, "after one and after two"),
        (1285.0, "much later"),
    ]


def test_the_same_words_said_again_later_in_a_chunk_are_kept():
    first = _srt((10, 12, "Kyllä."))
    second = _srt((115, 116, "Kyllä."), (119, 120, "Kyllä."), (123, 124, "Kyllä."))

    assert [text for _, text in _merged(first, second)] == ["Kyllä."] * 4


def test_a_subtitle_both_chunks_place_at_the_boundary_is_kept_once():
    # The same sentence, timed just before the boundary by one chunk and just
    # after it by the other.
    first = _srt((1199.8, 1202.0, "Same words"))
    second = _srt((15.2, 17.4, "same words."), (30, 32, "next"))

    assert [text for _, text in _merged(first, second)] == ["Same words", "next"]


def test_the_trailing_overlap_is_kept_when_no_chunk_follows_it():
    first = _srt((1190, 1195, "before"), (1205, 1210, "only this chunk has it"))

    # The later chunk gave no transcript.
    for second in ("", "   "):
        assert [text for _, text in _merged(first, second)] == [
            "before",
            "only this chunk has it",
        ]
    # The later chunk was never made, so the metadata ends with this one.
    assert "only this chunk has it" in combine_srt_chunks([first, _srt((1, 2, "x"))], META[:1])


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "00:00:00,000"),
        (59.9996, "00:01:00,000"),
        (3599.9999, "01:00:00,000"),
        (3661.5, "01:01:01,500"),
        (1.0004, "00:00:01,000"),
    ],
)
def test_a_timestamp_never_shows_sixty_seconds(seconds, expected):
    assert seconds_to_time(seconds) == expected


def test_webvtt_changes_the_timestamps_and_leaves_the_text():
    srt = (
        "1\n00:00:01,000 --> 00:00:02,500\nWell, hello, world\n\n"
        "2\n01:02:03,004 --> 01:02:04,000\n1,5 kg"
    )

    vtt = ParallelTranscriber._convert_format(srt, "vtt")

    assert vtt == (
        "WEBVTT\n\n1\n00:00:01.000 --> 00:00:02.500\nWell, hello, world\n\n"
        "2\n01:02:03.004 --> 01:02:04.000\n1,5 kg"
    )


def test_a_failed_audio_extraction_leaves_no_temp_folder(tmp_path, monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError("ffmpeg failed")

    monkeypatch.setattr(pipeline_module, "has_video_stream", lambda _path: True)
    monkeypatch.setattr(pipeline_module, "has_audio_stream", lambda _path: True)
    monkeypatch.setattr(pipeline_module, "extract_audio", fail)
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"not a real video")
    pattern = os.path.join(tempfile.gettempdir(), "parallel_transcriber_*")
    before = set(glob.glob(pattern))

    with pytest.raises(RuntimeError, match="ffmpeg failed"):
        ParallelTranscriber({"api_key": "test"}).transcribe(video)

    assert set(glob.glob(pattern)) == before
