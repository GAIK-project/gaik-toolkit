"""The report writer keeps uploads inside its run folder and passes on only the page's options."""

from pathlib import Path

import pytest
from api.routers import report_writer
from fastapi import HTTPException


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("notes.md", "notes.md"),
        ("../../etc/notes.md", "notes.md"),
        ("..\\..\\notes.md", "notes.md"),
        ("/abs/path/notes.md", "notes.md"),
        ("C:\\Users\\x\\notes.md", "notes.md"),
        ("..", "upload"),
        ("", "upload"),
        (".env", "env"),
    ],
)
def test_an_upload_name_is_a_plain_name(given, expected):
    assert report_writer._upload_name(given, set()) == expected


def test_a_repeated_name_does_not_replace_the_first_upload():
    used: set[str] = set()
    names = [report_writer._upload_name(n, used) for n in ("a.md", "dir/a.md", "A.md", "a")]
    assert names == ["a.md", "a-2.md", "A-3.md", "a"]


def test_an_upload_cannot_take_the_run_folders_names():
    used = {"output", "transcripts"}
    assert report_writer._upload_name("output", used) == "output-2"


def test_only_the_options_the_page_sets_are_passed_on(tmp_path: Path):
    options = report_writer._run_options(
        {
            "parser_options": {"api_base": "https://elsewhere.example"},
            "transcriber_options": {
                "ctor": {"language": "fi", "output_dir": "/srv", "api_key": "x"},
                "run": {"file_path": "/srv/a.wav"},
            },
            "image_options": {"mode": "parse", "output_dir": "/srv"},
            "writer_options": {"model": "m", "temperature": 0.2, "base_url": "https://x"},
            "review_options": {"model": "r", "endpoint": "https://x"},
        },
        tmp_path,
    )
    assert options == {
        "parser_options": {},
        "transcriber_options": {
            "ctor": {"language": "fi", "output_dir": str(tmp_path / "transcripts")}
        },
        "image_options": {"mode": "parse"},
        "writer_options": {"model": "m", "temperature": 0.2},
        "review_options": {"model": "r"},
    }


def test_the_page_config_passes_unchanged(tmp_path: Path):
    options = report_writer._run_options(
        {
            "parser_options": {},
            "transcriber_options": {},
            "image_options": {"mode": "structured", "user_requirements": "tables"},
            "writer_options": {"model": "m", "reasoning_effort": "low"},
            "review_options": None,
        },
        tmp_path,
    )
    assert options["image_options"] == {"mode": "structured", "user_requirements": "tables"}
    assert options["writer_options"] == {"model": "m", "reasoning_effort": "low"}
    assert options["review_options"] is None
    assert options["transcriber_options"] == {"ctor": {"output_dir": str(tmp_path / "transcripts")}}


def test_an_example_file_outside_the_example_folder_is_not_served():
    import asyncio

    with pytest.raises(HTTPException) as caught:
        asyncio.run(report_writer.get_example_file("../report_config.json"))
    assert caught.value.status_code == 404
