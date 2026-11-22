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


def test_a_pure_path_object_is_tagged_in_each_spelling():
    given = PurePosixPath("/srv/Matti Virtanen/report.pdf")

    text = error_text(ValueError(f"{given} and {given.as_posix()} and {given.name}"), given)

    assert text.count(file_tag(given)) == 3
    _assert_tagged(text, given)


def test_the_name_and_stem_are_still_tagged_and_a_tag_is_not_rewritten():
    # The stem "file" is also the first word of every tag.
    given = "C:/data/Matti Virtanen/file.pdf"

    text = error_text(ValueError("bad file.pdf, see file"), given)

    assert text == f"ValueError: bad {file_tag(given)}, see {file_tag(given)}"


def test_other_text_is_left_as_it_is():
    text = error_text(ValueError("page 3 has no text layer"), "C:/Users/Matti Virtanen/a.pdf")

    assert text == "ValueError: page 3 has no text layer"
