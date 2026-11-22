"""Tests for parallel_transcriber FFmpeg chunking reliability."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from gaik.software_components.parallel_transcriber.config import TranscriptionConfig
from gaik.software_components.parallel_transcriber.ffmpeg import (
    compute_chunk_specs,
    split_into_chunks,
)
from gaik.software_components.parallel_transcriber.models import ChunkSpec

# The mocked FFmpeg below writes 1000 bytes per second of audio; the chunk's
# length is read back from its size instead of with ffprobe.
_BYTES_PER_SECOND = 1000


@pytest.fixture
def real_ffprobe():
    """Read chunk lengths with the real ffprobe."""


@pytest.fixture(autouse=True)
def _chunk_length_from_size(request):
    if "real_ffprobe" in request.fixturenames:
        yield
        return
    with patch(
        "gaik.software_components.parallel_transcriber.ffmpeg._encoded_seconds",
        side_effect=lambda path: Path(path).stat().st_size / _BYTES_PER_SECOND,
    ):
        yield


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


def _split(tmp_path: Path, seconds: dict[str, list[float | None]]):
    """Split three chunks (0-65 s, 55-120 s, 115-180 s, the last); each attempt at a
    chunk writes the next length in its list, its last one again once the list runs
    out, or fails when the length is None. Chunks not named come out at 65 s.
    Chunk files are named chunk_00.mp3 to chunk_02.mp3."""
    specs = [_make_spec(0, tmp_path), _make_spec(1, tmp_path), _make_spec(2, tmp_path)]
    specs[2].is_last = True
    attempts = {name: list(values) for name, values in seconds.items()}
    calls: list[str] = []

    def fake_popen(cmd, **kwargs):
        chunk_path = Path(cmd[-1])
        calls.append(chunk_path.name)
        planned = attempts.get(chunk_path.name, [65.0])
        length = planned.pop(0) if len(planned) > 1 else planned[0]
        mock = MagicMock()
        if length is None:
            mock.returncode = 1
            mock.communicate.return_value = ("", "busy")
        else:
            chunk_path.write_bytes(b"\x00" * int(length * _BYTES_PER_SECOND))
            mock.returncode = 0
            mock.communicate.return_value = ("", "")
        return mock

    with _FFMPEG_AVAILABLE, patch("subprocess.Popen", side_effect=fake_popen):
        return split_into_chunks(str(tmp_path / "input.mp3"), specs), calls


def _indices(chunks: list[dict]) -> list[int]:
    return [c["metadata"]["index"] for c in chunks]


def test_chunks_past_the_real_end_are_skipped(tmp_path: Path):
    # A header that says 180 s for a recording of 100 s: the second chunk ends early
    # and the third holds nothing.
    chunks, _ = _split(tmp_path, {"chunk_01.mp3": [45.0], "chunk_02.mp3": [0.0]})

    assert _indices(chunks) == [0, 1]
    assert not (tmp_path / "chunk_02.mp3").exists()


def test_a_chunk_whose_audio_lies_inside_the_previous_one_is_skipped(tmp_path: Path):
    # The recording ends at 118 s, inside the second chunk's end overlap: the third
    # chunk's 3 s are already in the second.
    chunks, _ = _split(tmp_path, {"chunk_02.mp3": [3.0]})

    assert _indices(chunks) == [0, 1]


def test_a_short_chunk_with_audio_after_it_raises_with_its_time_range(tmp_path: Path):
    with pytest.raises(RuntimeError) as raised:
        _split(tmp_path, {"chunk_01.mp3": [10.0]})

    message = str(raised.value)
    assert "1 of 3 chunks could not be created" in message
    assert "(0:00:55-0:02:00)" in message
    assert "holds 10.0 s of 65.0 s, with audio after it" in message


def test_a_short_chunk_from_the_parallel_pass_is_retried(tmp_path: Path):
    chunks, calls = _split(tmp_path, {"chunk_01.mp3": [10.0, 65.0]})

    assert _indices(chunks) == [0, 1, 2]
    assert calls.count("chunk_01.mp3") == 2  # the parallel pass and the retry


def test_a_retried_chunk_that_comes_out_empty_at_the_end_is_skipped(tmp_path: Path):
    chunks, _ = _split(tmp_path, {"chunk_01.mp3": [None, 0.0], "chunk_02.mp3": [0.0]})

    assert _indices(chunks) == [0]


def test_a_retried_chunk_that_comes_out_short_before_audio_raises(tmp_path: Path):
    with pytest.raises(RuntimeError, match=r"\(0:00:55-0:02:00\)"):
        _split(tmp_path, {"chunk_01.mp3": [None, 10.0]})


def test_a_split_in_which_no_chunk_holds_audio_raises(tmp_path: Path):
    empty = {name: [0.0] for name in ("chunk_00.mp3", "chunk_01.mp3", "chunk_02.mp3")}

    with pytest.raises(RuntimeError, match="None of the 3 chunks holds any audio"):
        _split(tmp_path, empty)


def test_a_chunk_whose_length_cannot_be_read_raises_instead_of_being_dropped(tmp_path: Path):
    # Reading the last chunk's length times out on both attempts: it may hold audio, so
    # the split stops with its time range instead of dropping it as an empty tail.
    def timed_out_for_the_last(path):
        if Path(path).name == "chunk_02.mp3":
            return None
        return Path(path).stat().st_size / _BYTES_PER_SECOND

    with patch(
        "gaik.software_components.parallel_transcriber.ffmpeg._encoded_seconds",
        side_effect=timed_out_for_the_last,
    ):
        with pytest.raises(RuntimeError) as raised:
            _split(tmp_path, {})

    message = str(raised.value)
    assert "(0:01:55-0:03:00)" in message
    assert "the length of chunk 3 could not be read" in message


def test_a_probe_timeout_is_an_unknown_length_not_an_empty_chunk(tmp_path: Path, real_ffprobe):
    from gaik.software_components.parallel_transcriber import ffmpeg

    chunk = tmp_path / "chunk_00.mp3"
    chunk.write_bytes(b"\x00" * 10)
    with patch.object(
        ffmpeg, "get_audio_duration", side_effect=subprocess.TimeoutExpired("ffprobe", 1)
    ):
        assert ffmpeg._encoded_seconds(chunk) is None
    with patch.object(ffmpeg, "get_audio_duration", side_effect=ValueError("no audio")):
        assert ffmpeg._encoded_seconds(chunk) == 0.0


_HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


@pytest.mark.skipif(not _HAS_FFMPEG, reason="needs ffmpeg and ffprobe on PATH")
@pytest.mark.parametrize("header_seconds", [120.5, 300.0])
def test_a_low_bitrate_split_keeps_every_chunk_of_the_recording(
    tmp_path: Path, header_seconds: float, real_ffprobe
):
    # At 8 kbit/s a full 65-second chunk is about 65 KB. 300 s is a header that
    # overstates the length of the 120.5-second recording.
    source = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=120.5"]
        + ["-ar", "16000", "-ac", "1", "-y", str(source)],
        check=True,
        timeout=60,
    )
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir()
    specs = compute_chunk_specs(header_seconds, 1, 5.0, chunk_dir, "tone")

    chunks = split_into_chunks(source, specs, config=TranscriptionConfig(audio_bitrate="8k"))

    assert _indices(chunks) == [0, 1]
    assert all(Path(c["file"]).stat().st_size < 0.1 * 1024 * 1024 for c in chunks)


# -- a real tail shorter than the tolerance is kept (#300 item 1) -------------------


def test_a_tail_under_a_second_past_the_previous_chunk_is_kept(tmp_path: Path):
    # The second chunk covers up to 120 s; the recording ends at 120.8 s, inside the
    # third chunk (115-120.8 s): its last 0.8 s are in no other chunk.
    chunks, _ = _split(tmp_path, {"chunk_02.mp3": [5.8]})

    assert _indices(chunks) == [0, 1, 2]


@pytest.mark.parametrize(("last_seconds", "kept"), [(5.2, [0, 1]), (5.3, [0, 1, 2])])
def test_a_tail_of_a_quarter_second_or_less_is_not_sent(
    tmp_path: Path, last_seconds: float, kept: list[int]
):
    # The third chunk (115 s on) adds 0.2 s or 0.3 s past the second's end at 120 s:
    # a model asked about 0.2 s of near-silence can make words up.
    chunks, _ = _split(tmp_path, {"chunk_02.mp3": [last_seconds]})

    assert _indices(chunks) == kept


def test_a_chunk_that_holds_only_a_fraction_of_a_second_is_not_sent(tmp_path: Path):
    # Two minutes in the header, no overlap, and the audio ends 0.11 s into the second
    # chunk: it alone would be sent with 0.11 s of audio.
    specs = compute_chunk_specs(120.0, 1, 0.0, tmp_path, "rec")
    lengths = {"rec_chunk_01.mp3": 60.0, "rec_chunk_02.mp3": 0.11}

    def encoder(cmd, **_kwargs):
        Path(cmd[-1]).write_bytes(b"\x00" * int(lengths[Path(cmd[-1]).name] * _BYTES_PER_SECOND))
        process = MagicMock()
        process.returncode = 0
        process.communicate.return_value = ("", "")
        return process

    with _FFMPEG_AVAILABLE, patch("subprocess.Popen", side_effect=encoder):
        chunks = split_into_chunks(str(tmp_path / "rec.mp3"), specs)

    assert _indices(chunks) == [0]


def _exact_encoder(cmd, **_kwargs):
    """A fake FFmpeg that encodes exactly the -t seconds it is asked for."""
    seconds = float(cmd[cmd.index("-t") + 1])
    Path(cmd[-1]).write_bytes(b"\x00" * int(round(seconds * _BYTES_PER_SECOND)))
    process = MagicMock()
    process.returncode = 0
    process.communicate.return_value = ("", "")
    return process


@pytest.mark.parametrize("recording_seconds", [1216.0, 1215.8])
def test_the_default_split_keeps_the_end_of_the_recording(tmp_path: Path, recording_seconds: float):
    # 20-minute chunks with 15 s overlaps: the first chunk covers 0-1215 s, so the
    # second (1185 s to the end) holds the last 1.0 s or 0.8 s that no other chunk has.
    defaults = TranscriptionConfig()
    specs = compute_chunk_specs(
        recording_seconds,
        defaults.chunk_duration_minutes,
        defaults.chunk_overlap_seconds,
        tmp_path,
        "rec",
    )
    assert [(s.actual_start, s.actual_start + s.duration) for s in specs] == [
        (0, 1215.0),
        (1185.0, recording_seconds),
    ]

    with _FFMPEG_AVAILABLE, patch("subprocess.Popen", side_effect=_exact_encoder):
        chunks = split_into_chunks(str(tmp_path / "rec.mp3"), specs)

    assert _indices(chunks) == [0, 1]


@pytest.mark.skipif(not _HAS_FFMPEG, reason="needs ffmpeg and ffprobe on PATH")
def test_a_real_tail_of_0_8_seconds_is_kept_with_real_ffmpeg(tmp_path: Path, real_ffprobe):
    # 1-minute chunks with 5 s overlaps on 125.8 s: the second chunk covers 55-125 s and
    # the third (115-125.8 s) holds the last 0.8 s.
    source = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=125.8"]
        + ["-ar", "16000", "-ac", "1", "-y", str(source)],
        check=True,
        timeout=60,
    )
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir()
    specs = compute_chunk_specs(125.8, 1, 5.0, chunk_dir, "tone")

    chunks = split_into_chunks(source, specs, config=TranscriptionConfig(audio_bitrate="8k"))

    assert _indices(chunks) == [0, 1, 2]


# -- chunk errors are logged without the file's folder or name (#305 item 2) ---------


def _private_recording(tmp_path: Path) -> tuple[Path, list[ChunkSpec]]:
    folder = tmp_path / "Matti Virtanen"
    folder.mkdir()
    recording = folder / "Matti_Virtanen_interview.mp3"
    recording.write_bytes(b"\x00" * 10)
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir()
    return recording, compute_chunk_specs(120.0, 1, 5.0, chunk_dir, recording.stem)


def _assert_no_name_in_logs(caplog, recording: Path) -> None:
    messages = [record.getMessage() for record in caplog.records]
    assert any("Chunk 1 failed" in m or "Error creating chunk 1" in m for m in messages)
    for message in messages:
        for private in (str(recording.parent), recording.name, "Matti", "Virtanen"):
            assert private not in message, message


def test_a_failing_encode_logs_only_its_exit_code(tmp_path: Path, caplog):
    recording, specs = _private_recording(tmp_path)
    commands: list[list[str]] = []

    def failing_ffmpeg(cmd, **_kwargs):
        commands.append(cmd)
        process = MagicMock()
        process.returncode = 1
        process.communicate.return_value = (
            "",
            f"{recording.absolute()}: Invalid data found\n{cmd[-1]}: could not write",
        )
        return process

    with (
        caplog.at_level(logging.DEBUG),
        _FFMPEG_AVAILABLE,
        patch("subprocess.Popen", side_effect=failing_ffmpeg),
        pytest.raises(RuntimeError) as raised,
    ):
        split_into_chunks(str(recording), specs)

    _assert_no_name_in_logs(caplog, recording)
    assert any("FFmpeg exit 1" in record.getMessage() for record in caplog.records)
    # The caller still gets FFmpeg's message, and FFmpeg prints the error alone.
    assert "Invalid data found" in str(raised.value)
    assert commands[0][:4] == ["ffmpeg", "-hide_banner", "-loglevel", "error"]


def test_an_encode_that_cannot_start_logs_no_file_name(tmp_path: Path, caplog):
    recording, specs = _private_recording(tmp_path)

    def cannot_start(cmd, **_kwargs):
        raise OSError(2, "No such file or directory", cmd[-1])

    with (
        caplog.at_level(logging.DEBUG),
        _FFMPEG_AVAILABLE,
        patch("subprocess.Popen", side_effect=cannot_start),
        pytest.raises(RuntimeError),
    ):
        split_into_chunks(str(recording), specs)

    _assert_no_name_in_logs(caplog, recording)
    assert any("FileNotFoundError" in record.getMessage() for record in caplog.records)


def test_a_relative_input_and_a_private_chunk_folder_stay_out_of_the_log(
    tmp_path: Path, caplog, monkeypatch
):
    # The input is given relative to its folder, whose name holds the input's stem, and
    # the chunks go to a temporary folder under the user's home, as on Windows.
    home = tmp_path / "Matti Virtanen"
    folder = home / "interviews"
    folder.mkdir(parents=True)
    recording = folder / "interview.mp3"
    recording.write_bytes(b"\x00" * 10)
    chunk_dir = home / "AppData" / "Local" / "Temp" / "parallel_transcriber_chunks_abc"
    chunk_dir.mkdir(parents=True)
    specs = compute_chunk_specs(120.0, 1, 5.0, chunk_dir, recording.stem)
    monkeypatch.chdir(folder)

    def cannot_start(cmd, **_kwargs):
        # Chunk 1 names the absolute input, chunk 2 its own chunk file.
        named = str(recording) if cmd[-1].endswith("_01.mp3") else cmd[-1]
        raise OSError(2, "No such file or directory", named)

    with (
        caplog.at_level(logging.DEBUG),
        _FFMPEG_AVAILABLE,
        patch("subprocess.Popen", side_effect=cannot_start),
        pytest.raises(RuntimeError),
    ):
        split_into_chunks("interview.mp3", specs)

    messages = [record.getMessage() for record in caplog.records]
    assert any("Error creating chunk 1" in m for m in messages)
    assert any("Error creating chunk 2" in m for m in messages)
    for message in messages:
        for private in (str(tmp_path), str(home), "Matti", "Virtanen", "interview"):
            assert private not in message, message


def test_a_file_named_like_a_word_leaves_that_word_in_the_log(tmp_path: Path):
    # A recording named audio.mp3: the path is tagged, the word "audio" in the error is not.
    from gaik.software_components.parallel_transcriber.ffmpeg import _paths_tagged

    recording = tmp_path / "Matti Virtanen" / "audio.mp3"
    chunk = tmp_path / "chunks" / "audio_chunk_01.mp3"
    error = OSError(2, "could not decode the audio stream of audio", str(recording))

    text = _paths_tagged(error, "audio.mp3", recording, chunk)

    assert "could not decode the audio stream of audio" in text
    assert "Matti" not in text and str(tmp_path) not in text
    # The names and stems themselves are still tagged where they stand as names.
    for message in (f"cannot write {chunk.name}", f"'{chunk.stem}'", "'audio' or audio.mp3"):
        tagged = _paths_tagged(OSError(message), "audio.mp3", recording, chunk)
        assert "audio_chunk" not in tagged and "'audio'" not in tagged, tagged
        assert "audio.mp3" not in tagged, tagged
    # Only a whole word: another file whose name ends in the same letters stays.
    assert "myaudio.mp3" in _paths_tagged(OSError("see myaudio.mp3"), "audio.mp3")
