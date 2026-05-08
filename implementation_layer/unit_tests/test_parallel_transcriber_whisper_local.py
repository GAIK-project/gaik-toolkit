"""Tests for the WHISPER_LOCAL transcription path in ParallelTranscriber."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from gaik.software_components.parallel_transcriber import (
    ParallelTranscriber,
    TranscriptionConfig,
    TranscriptionModel,
)


def _api_cfg(**overrides) -> dict:
    base = {"api_base": "http://whisper.example.com:8080", "key": "test-key"}
    base.update(overrides)
    return base


class TestConstructor:
    def test_whisper_local_requires_api_base(self):
        cfg = TranscriptionConfig(model=TranscriptionModel.WHISPER_LOCAL)
        with pytest.raises(ValueError, match="api_base"):
            ParallelTranscriber({}, cfg)

    def test_whisper_local_skips_openai_provider_check(self):
        cfg = TranscriptionConfig(model=TranscriptionModel.WHISPER_LOCAL)
        # Bare api_base+key is enough; no use_azure / provider needed.
        ParallelTranscriber(_api_cfg(), cfg)

    def test_cloud_models_still_require_openai_or_azure(self):
        cfg = TranscriptionConfig(model=TranscriptionModel.WHISPER)
        with pytest.raises(NotImplementedError):
            ParallelTranscriber({"provider": "anthropic"}, cfg)


class TestSegmentsToSrt:
    def test_basic_segments(self):
        srt = ParallelTranscriber._whisper_local_segments_to_srt(
            [
                {"start": 0.0, "end": 1.5, "text": "Hello"},
                {"start": 1.5, "end": 3.0, "text": "World"},
            ]
        )
        assert "00:00:00,000 --> 00:00:01,500" in srt
        assert "Hello" in srt
        assert "00:00:01,500 --> 00:00:03,000" in srt
        assert "World" in srt

    def test_empty_text_skipped(self):
        srt = ParallelTranscriber._whisper_local_segments_to_srt(
            [
                {"start": 0.0, "end": 1.0, "text": ""},
                {"start": 1.0, "end": 2.0, "text": "Real"},
            ]
        )
        assert srt.count("-->") == 1
        assert "Real" in srt


class TestTooLongAudioRejected:
    def test_audio_over_max_minutes_raises(self, tmp_path: Path):
        audio = tmp_path / "huge.mp3"
        audio.write_bytes(b"\x00" * 64)  # presence is enough; we mock duration

        cfg = TranscriptionConfig(
            model=TranscriptionModel.WHISPER_LOCAL,
            whisper_local_max_audio_minutes=10.0,
        )
        transcriber = ParallelTranscriber(_api_cfg(), cfg)

        # 11 minutes exceeds the 10-minute cap; pipeline must fail fast.
        with patch(
            "gaik.software_components.parallel_transcriber.pipeline.has_video_stream",
            return_value=False,
        ), patch(
            "gaik.software_components.parallel_transcriber.pipeline.has_audio_stream",
            return_value=True,
        ), patch(
            "gaik.software_components.parallel_transcriber.pipeline.get_audio_duration",
            return_value=11 * 60,
        ):
            with pytest.raises(ValueError, match="Audio too long for whisper_local"):
                transcriber.transcribe(audio)


class TestSinglePassWhisperLocal:
    def test_short_audio_uses_single_pass(self, tmp_path: Path):
        audio = tmp_path / "short.mp3"
        audio.write_bytes(b"\x00" * 64)

        cfg = TranscriptionConfig(
            model=TranscriptionModel.WHISPER_LOCAL,
            max_single_file_mb=1024.0,  # ensure size-based chunking does not kick in
            whisper_local_chunk_duration_minutes=20,
            whisper_local_max_audio_minutes=360.0,
        )
        transcriber = ParallelTranscriber(_api_cfg(), cfg)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "segments": [
                {"start": 0.0, "end": 2.0, "text": "Hi there"},
            ],
            "text": "Hi there",
        }
        mock_response.raise_for_status = MagicMock()

        with patch(
            "gaik.software_components.parallel_transcriber.pipeline.has_video_stream",
            return_value=False,
        ), patch(
            "gaik.software_components.parallel_transcriber.pipeline.has_audio_stream",
            return_value=True,
        ), patch(
            "gaik.software_components.parallel_transcriber.pipeline.get_audio_duration",
            return_value=120.0,  # 2 min — under chunk_duration_minutes
        ), patch("requests.post", return_value=mock_response):
            result = transcriber.transcribe(audio)

        assert result.format == "srt"
        assert "Hi there" in result.content
        assert result.total_chunks == 1


class TestChunkedWhisperLocal:
    def test_long_audio_chunks_and_combines(self, tmp_path: Path):
        audio = tmp_path / "long.mp3"
        audio.write_bytes(b"\x00" * 64)

        cfg = TranscriptionConfig(
            model=TranscriptionModel.WHISPER_LOCAL,
            max_single_file_mb=1024.0,
            whisper_local_chunk_duration_minutes=20,
            whisper_local_chunk_parallelism=2,
            whisper_local_max_audio_minutes=360.0,
        )
        transcriber = ParallelTranscriber(_api_cfg(), cfg)

        # 2 fake chunks the splitter would have produced
        chunk_paths = [str(tmp_path / "chunk_01.mp3"), str(tmp_path / "chunk_02.mp3")]
        for p in chunk_paths:
            Path(p).write_bytes(b"\x00")
        chunk_metadata = [
            {"index": 0, "nominal_start": 0.0, "actual_start": 0.0,
             "overlap_start": 0.0, "overlap_end": 15.0},
            {"index": 1, "nominal_start": 1200.0, "actual_start": 1185.0,
             "overlap_start": 15.0, "overlap_end": 0.0},
        ]

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "segments": [{"start": 0.0, "end": 5.0, "text": "Chunk text"}],
            "text": "Chunk text",
        }
        mock_response.raise_for_status = MagicMock()

        with patch(
            "gaik.software_components.parallel_transcriber.pipeline.has_video_stream",
            return_value=False,
        ), patch(
            "gaik.software_components.parallel_transcriber.pipeline.has_audio_stream",
            return_value=True,
        ), patch(
            "gaik.software_components.parallel_transcriber.pipeline.get_audio_duration",
            return_value=40 * 60,  # 40 min — forces chunking
        ), patch(
            "gaik.software_components.parallel_transcriber.pipeline.split_audio",
            return_value=(chunk_paths, chunk_metadata),
        ), patch(
            "requests.post", return_value=mock_response,
        ) as mock_post:
            result = transcriber.transcribe(audio)

        # One POST per chunk
        assert mock_post.call_count == 2
        # Combined SRT contains content from both chunks
        assert "Chunk text" in result.content
        assert result.total_chunks == 2
        assert result.format == "srt"

    def test_chunked_progress_callback_invoked(self, tmp_path: Path):
        audio = tmp_path / "long.mp3"
        audio.write_bytes(b"\x00" * 64)

        cfg = TranscriptionConfig(
            model=TranscriptionModel.WHISPER_LOCAL,
            max_single_file_mb=1024.0,
            whisper_local_chunk_duration_minutes=20,
            whisper_local_chunk_parallelism=1,  # serial for deterministic order
            whisper_local_max_audio_minutes=360.0,
        )
        transcriber = ParallelTranscriber(_api_cfg(), cfg)

        chunk_paths = [str(tmp_path / "c1.mp3"), str(tmp_path / "c2.mp3")]
        for p in chunk_paths:
            Path(p).write_bytes(b"\x00")
        chunk_metadata = [
            {"index": 0, "nominal_start": 0.0, "actual_start": 0.0,
             "overlap_start": 0.0, "overlap_end": 0.0},
            {"index": 1, "nominal_start": 1200.0, "actual_start": 1200.0,
             "overlap_start": 0.0, "overlap_end": 0.0},
        ]

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "segments": [{"start": 0.0, "end": 1.0, "text": "x"}],
            "text": "x",
        }
        mock_response.raise_for_status = MagicMock()

        events: list[tuple[str, int, int, str]] = []

        with patch(
            "gaik.software_components.parallel_transcriber.pipeline.has_video_stream",
            return_value=False,
        ), patch(
            "gaik.software_components.parallel_transcriber.pipeline.has_audio_stream",
            return_value=True,
        ), patch(
            "gaik.software_components.parallel_transcriber.pipeline.get_audio_duration",
            return_value=40 * 60,
        ), patch(
            "gaik.software_components.parallel_transcriber.pipeline.split_audio",
            return_value=(chunk_paths, chunk_metadata),
        ), patch("requests.post", return_value=mock_response):
            transcriber.transcribe(audio, progress_callback=lambda *args: events.append(args))

        transcribing = [e for e in events if e[0] == "transcribing"]
        assert len(transcribing) >= 2  # one per chunk
        assert all("whisper_local" in e[3] for e in transcribing)


class TestRequestPayload:
    def test_post_uses_configured_timeout_and_auth(self, tmp_path: Path):
        audio = tmp_path / "short.mp3"
        audio.write_bytes(b"\x00" * 64)

        cfg = TranscriptionConfig(
            model=TranscriptionModel.WHISPER_LOCAL,
            max_single_file_mb=1024.0,
            whisper_local_chunk_duration_minutes=20,
            whisper_local_request_timeout_seconds=42,
            whisper_local_max_audio_minutes=360.0,
            language="fi",
        )
        transcriber = ParallelTranscriber(_api_cfg(key="secret"), cfg)

        mock_response = MagicMock()
        mock_response.json.return_value = {"segments": [], "text": ""}
        mock_response.raise_for_status = MagicMock()

        with patch(
            "gaik.software_components.parallel_transcriber.pipeline.has_video_stream",
            return_value=False,
        ), patch(
            "gaik.software_components.parallel_transcriber.pipeline.has_audio_stream",
            return_value=True,
        ), patch(
            "gaik.software_components.parallel_transcriber.pipeline.get_audio_duration",
            return_value=60.0,
        ), patch("requests.post", return_value=mock_response) as mock_post:
            transcriber.transcribe(audio)

        # Verify request shape
        assert mock_post.call_count == 1
        kwargs = mock_post.call_args.kwargs
        assert kwargs["timeout"] == 42
        assert kwargs["headers"] == {"key": "secret"}
        assert kwargs["data"]["language"] == "fi"
        assert kwargs["data"]["diarization"] is False

        # URL
        url = mock_post.call_args.args[0]
        assert url == "http://whisper.example.com:8080/transcribe"
