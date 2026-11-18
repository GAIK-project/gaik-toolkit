"""Tests for parallel_transcriber FFmpeg chunking reliability."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from gaik.software_components.parallel_transcriber.ffmpeg import (
    split_into_chunks,
)
from gaik.software_components.parallel_transcriber.models import ChunkSpec


def _make_spec(index: int, tmp_path: Path) -> ChunkSpec:
    """Create a minimal ChunkSpec for testing."""
    spec = ChunkSpec(
        index=index,
        nominal_start=index * 60.0,
        actual_start=max(0, index * 60.0 - 5.0) if index > 0 else 0,
        duration=65.0,
        overlap_start=5.0 if index > 0 else 0,
        overlap_end=5.0,
        chunk_path=tmp_path / f"chunk_{index:02d}.mp3",
    )
    spec.is_last = False
    return spec


class TestSplitIntoChunksPreflight:
    """Tests for the FFmpeg preflight check."""

    def test_ffmpeg_missing_raises_runtime_error(self, tmp_path: Path):
        specs = [_make_spec(0, tmp_path)]
        with patch(
            "gaik.software_components.parallel_transcriber.ffmpeg.check_ffmpeg_available",
            return_value=False,
        ):
            with pytest.raises(RuntimeError, match="ffmpeg/ffprobe not found"):
                split_into_chunks("dummy.mp3", specs)

    def test_ffmpeg_available_passes_preflight(self, tmp_path: Path):
        """When FFmpeg is available but the file doesn't exist, we get past preflight."""
        specs = [_make_spec(0, tmp_path)]
        with patch(
            "gaik.software_components.parallel_transcriber.ffmpeg.check_ffmpeg_available",
            return_value=True,
        ):
            # Will fail at Popen (file doesn't exist), but preflight passes
            with pytest.raises(RuntimeError, match="could not be created"):
                split_into_chunks("nonexistent.mp3", specs)


class TestSplitIntoChunksErrors:
    """Tests for structured error reporting and retry."""

    @patch(
        "gaik.software_components.parallel_transcriber.ffmpeg.check_ffmpeg_available",
        return_value=True,
    )
    def test_all_chunks_fail_includes_error_detail(self, _mock_ffmpeg, tmp_path: Path):
        """When all chunks fail, the RuntimeError includes FFmpeg error details."""
        specs = [_make_spec(0, tmp_path), _make_spec(1, tmp_path)]

        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = ("", "encoder error: codec not found")

        with patch("subprocess.Popen", return_value=mock_process):
            with pytest.raises(RuntimeError, match="encoder error"):
                split_into_chunks("test.mp3", specs)

    @patch(
        "gaik.software_components.parallel_transcriber.ffmpeg.check_ffmpeg_available",
        return_value=True,
    )
    def test_error_message_not_generic(self, _mock_ffmpeg, tmp_path: Path):
        """Error message must NOT be the old generic 'No chunks were successfully created'."""
        specs = [_make_spec(0, tmp_path)]

        mock_process = MagicMock()
        mock_process.returncode = 127
        mock_process.communicate.return_value = ("", "ffmpeg: command not found")

        with patch("subprocess.Popen", return_value=mock_process):
            with pytest.raises(RuntimeError) as exc_info:
                split_into_chunks("test.mp3", specs)
            # Must contain actual error, not just "No chunks"
            assert "FFmpeg exit 127" in str(exc_info.value)


class TestSplitIntoChunksRetry:
    """Tests for sequential retry of failed chunks."""

    @patch(
        "gaik.software_components.parallel_transcriber.ffmpeg.check_ffmpeg_available",
        return_value=True,
    )
    def test_retry_recovers_failed_chunks(self, _mock_ffmpeg, tmp_path: Path):
        """Chunks that fail in parallel pass but succeed on retry are included."""
        specs = [_make_spec(0, tmp_path)]
        specs[0].is_last = True

        call_count = 0

        def fake_popen(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            mock = MagicMock()
            if call_count == 1:
                # First call (parallel): fail
                mock.returncode = 1
                mock.communicate.return_value = ("", "transient error")
            else:
                # Second call (retry): succeed — create the output file
                chunk_path = Path(cmd[-1])  # last arg is output path
                chunk_path.write_bytes(b"\x00" * 200_000)  # 200KB fake chunk
                mock.returncode = 0
                mock.communicate.return_value = ("", "")
            return mock

        with patch("subprocess.Popen", side_effect=fake_popen):
            results = split_into_chunks(str(tmp_path / "input.mp3"), specs)

        assert len(results) == 1
        assert "file" in results[0]

    @patch(
        "gaik.software_components.parallel_transcriber.ffmpeg.check_ffmpeg_available",
        return_value=True,
    )
    def test_partial_success_still_retries_failures(self, _mock_ffmpeg, tmp_path: Path):
        """When some chunks succeed and some fail, failures are still retried."""
        specs = [_make_spec(0, tmp_path), _make_spec(1, tmp_path)]
        specs[1].is_last = True

        call_count = 0

        def fake_popen(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            mock = MagicMock()
            chunk_path = Path(cmd[-1])

            if call_count == 1:
                # Chunk 0 parallel: succeed
                chunk_path.write_bytes(b"\x00" * 200_000)
                mock.returncode = 0
                mock.communicate.return_value = ("", "")
            elif call_count == 2:
                # Chunk 1 parallel: fail
                mock.returncode = 1
                mock.communicate.return_value = ("", "busy")
            else:
                # Chunk 1 retry: succeed
                chunk_path.write_bytes(b"\x00" * 200_000)
                mock.returncode = 0
                mock.communicate.return_value = ("", "")
            return mock

        with patch("subprocess.Popen", side_effect=fake_popen):
            results = split_into_chunks(str(tmp_path / "input.mp3"), specs)

        assert len(results) == 2
        assert results[0]["metadata"]["index"] == 0
        assert results[1]["metadata"]["index"] == 1


class TestSplitIntoChunksNoGaps:
    """A chunk that cannot be created stops the split instead of leaving a gap."""

    @patch(
        "gaik.software_components.parallel_transcriber.ffmpeg.check_ffmpeg_available",
        return_value=True,
    )
    def test_a_chunk_that_fails_on_retry_raises_with_its_time_range(
        self, _mock_ffmpeg, tmp_path: Path
    ):
        specs = [_make_spec(0, tmp_path), _make_spec(1, tmp_path), _make_spec(2, tmp_path)]
        specs[2].is_last = True
        attempts: list[str] = []

        def fake_popen(cmd, **kwargs):
            chunk_path = Path(cmd[-1])
            attempts.append(chunk_path.name)
            mock = MagicMock()
            if chunk_path.name == "chunk_01.mp3":
                mock.returncode = 1
                mock.communicate.return_value = ("", "decode error")
            else:
                chunk_path.write_bytes(b"\x00" * 200_000)
                mock.returncode = 0
                mock.communicate.return_value = ("", "")
            return mock

        with patch("subprocess.Popen", side_effect=fake_popen):
            with pytest.raises(RuntimeError) as raised:
                split_into_chunks(str(tmp_path / "input.mp3"), specs)

        message = str(raised.value)
        assert "1 of 3 chunks could not be created" in message
        assert "(0:00:55-0:02:00)" in message
        assert "decode error" in message
        assert attempts.count("chunk_01.mp3") == 2  # the parallel pass and the retry


_FFMPEG_AVAILABLE = patch(
    "gaik.software_components.parallel_transcriber.ffmpeg.check_ffmpeg_available",
    return_value=True,
)


def _split(tmp_path: Path, sizes: dict[str, list[int | None]]):
    """Split three chunks; each attempt at a chunk writes the next size in its list,
    or fails when the size is None. Chunk files are named chunk_00.mp3 to chunk_02.mp3."""
    specs = [_make_spec(0, tmp_path), _make_spec(1, tmp_path), _make_spec(2, tmp_path)]
    specs[2].is_last = True
    attempts = {name: iter(values) for name, values in sizes.items()}

    def fake_popen(cmd, **kwargs):
        chunk_path = Path(cmd[-1])
        size = next(attempts[chunk_path.name]) if chunk_path.name in attempts else 200_000
        mock = MagicMock()
        if size is None:
            mock.returncode = 1
            mock.communicate.return_value = ("", "busy")
        else:
            chunk_path.write_bytes(b"\x00" * size)
            mock.returncode = 0
            mock.communicate.return_value = ("", "")
        return mock

    with _FFMPEG_AVAILABLE, patch("subprocess.Popen", side_effect=fake_popen):
        return split_into_chunks(str(tmp_path / "input.mp3"), specs)


def test_near_empty_chunks_past_the_real_end_are_skipped(tmp_path: Path):
    # A header that overstates the length gives near-empty chunks past the real end.
    chunks = _split(tmp_path, {"chunk_01.mp3": [10], "chunk_02.mp3": [10]})

    assert [c["metadata"]["index"] for c in chunks] == [0, 2]


def test_a_near_empty_chunk_with_audio_after_it_raises_with_its_time_range(tmp_path: Path):
    with pytest.raises(RuntimeError) as raised:
        _split(tmp_path, {"chunk_01.mp3": [10]})

    message = str(raised.value)
    assert "1 of 3 chunks could not be created" in message
    assert "(0:00:55-0:02:00)" in message
    assert "nearly empty" in message


def test_a_retried_chunk_that_comes_out_near_empty_at_the_end_is_skipped(tmp_path: Path):
    chunks = _split(tmp_path, {"chunk_01.mp3": [None, 10], "chunk_02.mp3": [10]})

    assert [c["metadata"]["index"] for c in chunks] == [0, 2]


def test_a_retried_chunk_that_comes_out_near_empty_before_audio_raises(tmp_path: Path):
    with pytest.raises(RuntimeError, match=r"\(0:00:55-0:02:00\)"):
        _split(tmp_path, {"chunk_01.mp3": [None, 10]})
