"""The PDF check runs in a process of its own, which is stopped at a deadline.

The check's outcomes come back as the check gives them. A process that does
not end, fails or answers nothing is refused for; while it runs, the API's
other threads keep running. The processes that stand in for a check here are
small scripts; every file is generated here.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
import zlib

import pytest
from api.utils import pdf_content, pdf_process
from api.utils.pdf_content import ActiveContentError, TooComplexError
from api.utils.upload_check import content_problem

PLAIN = (
    b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
    b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
)


def _with(extra: bytes) -> bytes:
    return PLAIN.replace(b"trailer", extra + b"trailer")


def _outcome(check, data: bytes) -> str:
    try:
        check(data)
    except ActiveContentError as exc:
        return f"active: {exc}"
    except TooComplexError as exc:
        return f"complex: {exc}"
    return "pass"


@pytest.fixture
def stand_in(monkeypatch):
    """Runs the given script instead of the check, with no spare processes."""
    started: list = []
    real_start = pdf_process._start
    python = pdf_process._command()[0]  # the interpreter a check runs on

    def use(script: str) -> list:
        monkeypatch.setattr(pdf_process, "_spares", [])
        monkeypatch.setattr(pdf_process, "SPARE_PROCESSES", 0)
        monkeypatch.setattr(pdf_process, "_command", lambda: [python, "-I", "-S", "-c", script])

        def start():
            process = real_start()
            started.append(process)
            return process

        monkeypatch.setattr(pdf_process, "_start", start)
        return started

    return use


def _stalls_while(work) -> tuple[float, object]:
    """The longest this thread waited for the interpreter while ``work`` ran."""
    result: dict = {}

    def run():
        result["value"] = _outcome(work, PLAIN)

    thread = threading.Thread(target=run)
    thread.start()
    longest = 0.0
    while thread.is_alive():
        start = time.perf_counter()
        time.sleep(0.005)
        longest = max(longest, time.perf_counter() - start)
    thread.join()
    return longest, result["value"]


@pytest.mark.parametrize(
    "data",
    [
        PLAIN,
        _with(b"3 0 obj\n<< /S /JavaScript /JS (app.alert(1)) >>\nendobj\n"),
        _with(b"3 0 obj\n<< /Length 1 /Filter /Unknown >>\nstream\nx\nendstream\nendobj\n"),
        _with(
            b"3 0 obj\n<< /Filter /FlateDecode >>\nstream\n"
            + zlib.compress(b"<< /S /Launch /F (x) >>")
            + b"\nendstream\nendobj\n"
        ),
        b"",
    ],
)
def test_the_check_in_its_own_process_gives_the_checks_own_outcome(data):
    assert _outcome(pdf_process.check, data) == _outcome(pdf_content.check, data)


def test_the_upload_check_reads_pdfs_in_the_checks_own_process(stand_in):
    started = stand_in(
        "import sys; sys.stdin.buffer.read(); "
        'print(\'{"outcome": "active", "message": "from the process"}\')'
    )
    assert content_problem(".pdf", PLAIN) == "From the process."
    assert len(started) == 1


def test_a_check_that_does_not_end_is_stopped_and_other_threads_keep_running(stand_in, monkeypatch):
    # The stand-in holds its own interpreter, as a long pattern search does.
    started = stand_in("import sys\nif sys.stdin.buffer.read():\n    while True: pass")
    monkeypatch.setattr(pdf_process, "PROCESS_SECONDS", 1.0)
    start = time.monotonic()
    longest, outcome = _stalls_while(pdf_process.check)
    assert outcome == f"complex: {pdf_content.TOO_COMPLEX}"
    assert time.monotonic() - start < 10
    assert longest < 0.5
    assert started[0].poll() is not None  # stopped, not left running


@pytest.mark.parametrize(
    "script",
    [
        "import sys; sys.stdin.buffer.read(); sys.exit(3)",
        "import sys; sys.stdin.buffer.read(); print('not an outcome')",
        'import sys; sys.stdin.buffer.read(); print(\'{"outcome": "maybe", "message": ""}\')',
    ],
)
def test_a_process_that_fails_or_gives_no_outcome_is_not_checkable(stand_in, script):
    stand_in(script)
    assert _outcome(pdf_process.check, PLAIN) == f"complex: {pdf_content.NOT_CHECKABLE}"


def test_a_process_that_goes_away_while_the_file_is_sent_is_not_checkable(stand_in, monkeypatch):
    stand_in("pass")

    class Gone:
        killed = False

        def poll(self):
            return None

        def communicate(self, data=None, timeout=None):
            raise OSError(22, "the pipe is gone")

        def kill(self):
            Gone.killed = True

    monkeypatch.setattr(pdf_process, "_start", Gone)
    assert _outcome(pdf_process.check, PLAIN) == f"complex: {pdf_content.NOT_CHECKABLE}"
    assert Gone.killed


def test_a_check_that_cannot_start_its_process_is_not_checkable(stand_in, monkeypatch):
    stand_in("pass")

    def fail():
        raise OSError("no processes here")

    monkeypatch.setattr(pdf_process, "_start", fail)
    assert _outcome(pdf_process.check, PLAIN) == f"complex: {pdf_content.NOT_CHECKABLE}"


def test_the_checks_process_keeps_none_of_the_apis_settings(stand_in, monkeypatch):
    monkeypatch.setenv("DEMO_TEST_SECRET", "not for the check")
    stand_in(
        "import os, sys; sys.stdin.buffer.read(); "
        "kind = 'active' if 'DEMO_TEST_SECRET' in os.environ else 'pass'; "
        'print(\'{"outcome": "%s", "message": "inherited"}\' % kind)'
    )
    assert _outcome(pdf_process.check, PLAIN) == "pass"


def test_a_spare_process_waits_for_the_next_check_and_ends_with_the_api(monkeypatch):
    monkeypatch.setattr(pdf_process, "_spares", [])
    monkeypatch.setattr(pdf_process, "SPARE_PROCESSES", 1)
    assert _outcome(pdf_process.check, PLAIN) == "pass"
    (spare,) = pdf_process._spares
    assert spare.poll() is None  # started, waiting for a file
    first = spare
    assert _outcome(pdf_process.check, PLAIN) == "pass"
    assert first.poll() == 0  # it checked that file and ended
    (spare,) = pdf_process._spares
    spare.stdin.close()  # as when the API ends: no file comes
    assert spare.wait(timeout=10) == 0
    assert spare.stdout.read() == b""


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the limits are set on Linux")
def test_the_checks_process_is_capped_in_memory_and_runs_at_a_lower_priority():
    probe = (
        "import importlib.util, os, sys\n"
        "spec = importlib.util.spec_from_file_location('pdf_content', sys.argv[1])\n"
        "module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)\n"
        "before = os.nice(0)\n"
        "module._limit_process(256 * 1024 * 1024)\n"
        "try:\n"
        "    bytearray(512 * 1024 * 1024)\n"
        "    capped = False\n"
        "except MemoryError:\n"
        "    capped = True\n"
        "print(capped, os.nice(0) - before)\n"
    )
    out = subprocess.run(
        [sys.executable, "-I", "-S", "-c", probe, pdf_content.__file__],
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout.split()
    assert out == [b"True", b"10"]


def test_a_limit_the_checks_process_cannot_set_is_said_not_passed_over(monkeypatch, capsys):
    """A refused memory cap or priority leaves the process running without it."""

    class Resource:
        RLIMIT_AS = 9
        RLIM_INFINITY = -1

        @staticmethod
        def getrlimit(kind):
            return (-1, -1)

        @staticmethod
        def setrlimit(kind, limits):
            raise ValueError("current limit exceeds maximum limit")

    def no_nice(increment):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setitem(sys.modules, "resource", Resource)
    monkeypatch.setattr(pdf_content.os, "nice", no_nice, raising=False)
    pdf_content._limit_process(256 * 1024 * 1024)

    captured = capsys.readouterr()
    assert captured.out == ""  # stdout carries only the outcome
    lines = captured.err.splitlines()
    assert len(lines) == 2
    assert all(line.startswith(pdf_content.LIMIT_NOTICE) for line in lines)
    assert "no memory cap" in lines[0] and "no lower priority" in lines[1]


def _refuses_the_memory_cap(stand_in, detail: str = "x") -> None:
    """Each check's process says it could not cap its memory, and passes the file."""
    stand_in(
        "import sys; sys.stdin.buffer.read(); "
        f"sys.stderr.write({pdf_content.LIMIT_NOTICE + f'no memory cap (ValueError: {detail})'!r}); "
        "sys.stderr.write(chr(10) + 'something else' + chr(10)); "
        'print(\'{"outcome": "pass", "message": ""}\')'
    )


def _limit_warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == pdf_process.__name__]


def test_the_api_logs_a_limit_the_checks_process_could_not_set(stand_in, caplog, monkeypatch):
    monkeypatch.setattr(pdf_process, "_limits_logged", set())
    _refuses_the_memory_cap(stand_in)
    with caplog.at_level("WARNING", logger=pdf_process.__name__):
        assert _outcome(pdf_process.check, PLAIN) == "pass"
    assert _limit_warnings(caplog) == [f"{pdf_content.LIMIT_NOTICE}no memory cap (ValueError: x)"]


def test_a_limit_every_checks_process_misses_is_logged_once(stand_in, caplog, monkeypatch):
    """macOS refuses the memory cap to every process: one warning, not one per file."""
    monkeypatch.setattr(pdf_process, "_limits_logged", set())
    with caplog.at_level("WARNING", logger=pdf_process.__name__):
        _refuses_the_memory_cap(stand_in, "x")
        assert _outcome(pdf_process.check, PLAIN) == "pass"
        _refuses_the_memory_cap(stand_in, "y")
        assert _outcome(pdf_process.check, PLAIN) == "pass"
        assert _outcome(pdf_process.check, PLAIN) == "pass"
    assert _limit_warnings(caplog) == [f"{pdf_content.LIMIT_NOTICE}no memory cap (ValueError: x)"]
