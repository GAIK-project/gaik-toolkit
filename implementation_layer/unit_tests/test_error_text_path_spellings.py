"""error_text tags a path however a message spells it.

It tagged the path as given, its doubled-backslash form, its name and its stem. A
library that normalizes the path first (``str(PurePath(...))``, ``as_posix()``, an
absolute or resolved path) printed a form it did not know, so the folder (which can
hold a person's name) stayed in the log line. The Windows and POSIX spellings are
checked on every platform.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest
from gaik.software_components._log_names import error_text, file_tag

PRIVATE = ("Matti", "Virtanen")


def _assert_tagged(text: str, path) -> None:
    for private in PRIVATE:
        assert private not in text, text
    assert file_tag(path) in text, text


@pytest.mark.parametrize(
    ("given", "printed"),
    [
        # Given with forward slashes on Windows; a library prints the native form.
        ("C:/Users/Matti Virtanen/report.pdf", "C:\\Users\\Matti Virtanen\\report.pdf"),
        # Given with backslashes; printed with as_posix().
        ("C:\\Users\\Matti Virtanen\\report.pdf", "C:/Users/Matti Virtanen/report.pdf"),
        # A UNC share, both ways.
        ("\\\\srv\\Matti Virtanen\\report.pdf", "//srv/Matti Virtanen/report.pdf"),
        # POSIX: "./" and a doubled slash are normalized away.
        ("./Matti Virtanen/report.pdf", "Matti Virtanen/report.pdf"),
        ("/home/Matti Virtanen//report.pdf", "/home/Matti Virtanen/report.pdf"),
        # A relative Windows path, printed normalized.
        (".\\Matti Virtanen\\report.pdf", "Matti Virtanen\\report.pdf"),
        # A ".." segment collapsed (os.path.normpath), with either separator.
        ("sub/../Matti Virtanen/report.pdf", "Matti Virtanen/report.pdf"),
        ("sub/../Matti Virtanen/report.pdf", "Matti Virtanen\\report.pdf"),
        ("sub\\..\\Matti Virtanen\\report.pdf", "Matti Virtanen/report.pdf"),
    ],
)
def test_a_normalized_spelling_of_the_path_is_tagged(given, printed):
    text = error_text(ValueError(f"cannot open {printed}"), given)

    assert text == f"ValueError: cannot open {file_tag(given)}"


@pytest.mark.parametrize(
    "given",
    ["C:/Users/Matti Virtanen/report.pdf", "C:\\Users\\Matti Virtanen\\report.pdf"],
)
def test_the_doubled_backslashes_of_a_normalized_path_are_tagged(given):
    # An OSError's message quotes the native Windows form with doubled backslashes.
    error = OSError(2, "No such file or directory", str(PureWindowsPath(given)))
    assert "\\\\Matti" in str(error)

    _assert_tagged(error_text(error, given), given)


def test_the_absolute_and_resolved_forms_of_a_relative_path_are_tagged(tmp_path, monkeypatch):
    folder = tmp_path / "Matti Virtanen"
    folder.mkdir()
    (folder / "report.pdf").write_bytes(b"%PDF-1.4")
    monkeypatch.chdir(tmp_path)
    given = os.path.join(".", "Matti Virtanen", "report.pdf")

    for printed in (
        os.path.abspath(given),
        str(Path(given).resolve()),
        Path(given).resolve().as_posix(),
    ):
        _assert_tagged(error_text(FileNotFoundError(f"no file {printed}"), given), given)


@pytest.mark.parametrize(
    "given",
    [
        PureWindowsPath("C:/srv/Matti Virtanen/report.pdf"),
        PurePosixPath("/srv/Matti Virtanen/report.pdf"),
    ],
)
def test_a_pure_path_object_is_tagged_in_each_spelling(given):
    # For a Windows path, str() and as_posix() are two spellings.
    windows = PureWindowsPath(given)
    message = f"{windows} and {windows.as_posix()} and {given.name}"

    text = error_text(ValueError(message), given)

    assert text.count(file_tag(given)) == 3
    _assert_tagged(text, given)


def test_the_stem_is_tagged_where_it_reads_as_a_file_name_and_a_tag_is_not_rewritten():
    # The stem "file" is also the first word of every tag.
    given = "C:/data/Matti Virtanen/file.pdf"

    text = error_text(ValueError("bad file.pdf, see 'file', file_chunk_001.wav"), given)

    tag = file_tag(given)
    assert text == f"ValueError: bad {tag}, see '{tag}', {tag}_chunk_001.wav"


@pytest.mark.parametrize(
    ("given", "message"),
    [
        # A stem that is also a word in the message, or part of the type name.
        ("/x/Value.txt", "bad value"),
        ("/x/file.csv", "The file is empty"),
        ("/x/data.csv", "no data in the data table"),
        ("/x/notes.pdf", "notes not ready; noted later"),
        ("/x/TODO", "TODO is a word here"),
        # A short stem inside a longer name or word is not the file.
        ("/x/data.csv", "'user_data' and metadata"),
        # What still passes, as documented: a short stem standing as a word.
        ("/x/notes.pdf", "cannot open notes (corrupt)"),
    ],
)
def test_a_stem_as_an_ordinary_word_and_the_type_name_are_left_alone(given, message):
    assert error_text(ValueError(message), given) == f"ValueError: {message}"


@pytest.mark.parametrize(
    ("given", "message", "expected"),
    [
        # A distinctive stem before a space, a parenthesis, punctuation or the end.
        ("/x/report.pdf", "cannot open report (corrupt)", "cannot open {tag} (corrupt)"),
        ("/x/Matti Virtanen.pdf", "cannot open Matti Virtanen.", "cannot open {tag}."),
        ("/x/scan01.png", "no text in scan01", "no text in {tag}"),
        ("/x/pöytäkirja.docx", "pöytäkirja, page 2", "{tag}, page 2"),
        # Not inside a longer word.
        ("/x/report.pdf", "reporting and myreport", "reporting and myreport"),
    ],
)
def test_a_distinctive_stem_is_tagged_as_a_word(given, message, expected):
    text = error_text(ValueError(message), given)

    assert text == "ValueError: " + expected.format(tag=file_tag(given))


def test_a_name_named_like_the_error_type_leaves_the_type_name():
    given = "/x/ValueError.txt"

    text = error_text(ValueError("cannot read ValueError.txt"), given)

    assert text == f"ValueError: cannot read {file_tag(given)}"


def test_a_file_named_after_the_stem_is_tagged():
    # A chunk or temporary file named after the input keeps the person's name.
    given = "/data/Matti_Virtanen_report.wav"

    text = error_text(RuntimeError("ffmpeg: /tmp/Matti_Virtanen_report_chunk_003.wav"), given)

    _assert_tagged(text, given)


def test_other_text_is_left_as_it_is():
    text = error_text(ValueError("page 3 has no text layer"), "C:/Users/Matti Virtanen/a.pdf")

    assert text == "ValueError: page 3 has no text layer"
