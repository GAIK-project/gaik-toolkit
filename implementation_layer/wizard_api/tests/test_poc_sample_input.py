"""Sample input for a sandbox run (#95).

A use case that needs a document to produce output cannot be demonstrated
without one, so the run view has to be able to hand the package a file.

The file lands in ``poc/sample_input/``, which is already served by the zip
endpoint and already unpacked by the Job's init container — the run reads it at
``/workspace/poc/sample_input`` with no change to the manifest, and regenerating
the package keeps it.

The rejection tests carry the weight here. The package root holds
``run_poc.py``, the file the sandbox Job executes, so a name that can climb out
of the input directory is the difference between handing the run some data and
handing it a different program.
"""

import os

import pytest
from wizard_api.services.poc_service import (
    MAX_INPUT_BYTES,
    UPLOADED_NAMES_FILE,
    InputRejectedError,
    delete_sample_input,
    list_sample_inputs,
    safe_input_name,
    save_sample_input,
    uploaded_sample_inputs,
)


@pytest.fixture
def poc(tmp_path):
    package = tmp_path / "poc"
    package.mkdir()
    (package / "run_poc.py").write_text(
        "from gaik.software_components.extractor import Extractor\n"
    )
    return str(package)


# ---------------------------------------------------------------------------
# What is accepted
# ---------------------------------------------------------------------------


def test_a_pdf_is_stored_in_the_input_directory(poc):
    name = save_sample_input(poc, "purchase-order.pdf", b"%PDF-1.7\n...")

    assert name == "purchase-order.pdf"
    assert os.path.isfile(os.path.join(poc, "sample_input", name))


def test_audio_works_the_same_way(poc):
    """UC01 is an audio case; the criteria name PDF and audio explicitly."""
    save_sample_input(poc, "incident.wav", b"RIFF....WAVE")

    assert [f["name"] for f in list_sample_inputs(poc)] == ["incident.wav"]


def test_the_listing_reports_the_size(poc):
    save_sample_input(poc, "a.pdf", b"12345")

    assert list_sample_inputs(poc) == [{"name": "a.pdf", "bytes": 5, "uploaded": True}]


def test_an_empty_package_lists_nothing(poc):
    assert list_sample_inputs(poc) == []


def test_an_input_can_be_removed(poc):
    save_sample_input(poc, "a.pdf", b"x")

    assert delete_sample_input(poc, "a.pdf") is True
    assert list_sample_inputs(poc) == []
    assert delete_sample_input(poc, "a.pdf") is False


# ---------------------------------------------------------------------------
# What is refused — the part that matters
# ---------------------------------------------------------------------------


def test_a_traversing_name_cannot_reach_the_package_root(poc):
    """This is the one that counts: ../run_poc.py is the file the Job runs."""
    with pytest.raises(InputRejectedError):
        save_sample_input(poc, "../run_poc.py", b"import os; os.system('id')")

    # The real entrypoint is untouched.
    assert "Extractor" in open(os.path.join(poc, "run_poc.py")).read()


def test_a_deeper_traversal_is_refused_too(poc):
    with pytest.raises(InputRejectedError):
        save_sample_input(poc, "../../../../etc/passwd", b"x")


def test_an_absolute_path_is_refused(poc):
    with pytest.raises(InputRejectedError):
        save_sample_input(poc, "/etc/passwd", b"x")


def test_a_windows_style_path_is_refused(poc):
    """A browser on Windows can send the whole path as the field's filename."""
    with pytest.raises(InputRejectedError):
        save_sample_input(poc, r"C:\\Windows\\System32\\drivers\\etc\\hosts", b"x")


def test_a_dotfile_is_refused(poc):
    with pytest.raises(InputRejectedError):
        save_sample_input(poc, ".env", b"AZURE_API_KEY=leak")


def test_an_empty_or_missing_name_is_refused(poc):
    for bad in ("", "   ", "."):
        with pytest.raises(InputRejectedError):
            save_sample_input(poc, bad, b"x")


def test_an_empty_file_is_refused(poc):
    with pytest.raises(InputRejectedError, match="empty"):
        save_sample_input(poc, "a.pdf", b"")


def test_a_file_over_the_limit_is_refused(poc):
    with pytest.raises(InputRejectedError, match="larger"):
        save_sample_input(poc, "big.wav", b"x" * (MAX_INPUT_BYTES + 1))


def test_a_name_that_is_all_separators_is_refused(poc):
    with pytest.raises(InputRejectedError):
        save_sample_input(poc, "///", b"x")


# ---------------------------------------------------------------------------
# The name rule on its own
# ---------------------------------------------------------------------------


def test_a_plain_name_passes_through():
    assert safe_input_name("invoice 2026-09.pdf") == "invoice 2026-09.pdf"


def test_a_directory_prefix_is_stripped_rather_than_honoured():
    """A browser may send a path; only the basename is ever used."""
    assert safe_input_name("uploads/2026/invoice.pdf") == "invoice.pdf"


def test_an_over_long_name_is_refused():
    with pytest.raises(InputRejectedError, match="too long"):
        safe_input_name("a" * 201 + ".pdf")


# ---------------------------------------------------------------------------
# Which files the user added (the run reads those before the package's examples)
# ---------------------------------------------------------------------------


def _example(poc, name):
    """A file the wizard wrote into sample_input/ itself, as its example input."""
    folder = os.path.join(poc, "sample_input")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name), "w") as fh:
        fh.write("example")


def test_an_uploaded_file_is_recorded_and_the_packages_example_is_not(poc):
    _example(poc, "delivery_note_sample.txt")

    save_sample_input(poc, "lahete.txt", b"LH-2026-11873")

    assert uploaded_sample_inputs(poc) == ["lahete.txt"]
    with open(os.path.join(poc, "sample_input", UPLOADED_NAMES_FILE)) as fh:
        assert fh.read() == "lahete.txt\n"


def test_the_record_is_not_listed_as_an_input(poc):
    _example(poc, "delivery_note_sample.txt")
    save_sample_input(poc, "lahete.txt", b"x")

    assert [f["name"] for f in list_sample_inputs(poc)] == [
        "delivery_note_sample.txt",
        "lahete.txt",
    ]


def test_the_listing_tells_the_users_file_from_the_wizards_example(poc):
    # The PoC tab starts its run by itself only on the user's own files.
    _example(poc, "delivery_note_sample.txt")
    save_sample_input(poc, "lahete.txt", b"x")

    assert [(f["name"], f["uploaded"]) for f in list_sample_inputs(poc)] == [
        ("delivery_note_sample.txt", False),
        ("lahete.txt", True),
    ]


def test_uploading_the_same_name_again_records_it_once(poc):
    save_sample_input(poc, "a.txt", b"1")
    save_sample_input(poc, "b.txt", b"2")
    save_sample_input(poc, "a.txt", b"3")

    assert uploaded_sample_inputs(poc) == ["b.txt", "a.txt"]


def test_deleting_an_upload_takes_it_off_the_record_and_the_last_one_removes_it(poc):
    save_sample_input(poc, "a.txt", b"1")
    save_sample_input(poc, "b.txt", b"2")

    assert delete_sample_input(poc, "a.txt") is True
    assert uploaded_sample_inputs(poc) == ["b.txt"]

    assert delete_sample_input(poc, "b.txt") is True
    assert uploaded_sample_inputs(poc) == []
    assert not os.path.exists(os.path.join(poc, "sample_input", UPLOADED_NAMES_FILE))


def test_deleting_the_packages_example_leaves_the_record_alone(poc):
    _example(poc, "sample.txt")
    save_sample_input(poc, "own.txt", b"1")

    assert delete_sample_input(poc, "sample.txt") is True
    assert uploaded_sample_inputs(poc) == ["own.txt"]


def test_the_record_cannot_be_uploaded_over_or_deleted_by_name(poc):
    save_sample_input(poc, "own.txt", b"1")

    with pytest.raises(InputRejectedError):
        save_sample_input(poc, UPLOADED_NAMES_FILE, b"other.txt")
    with pytest.raises(InputRejectedError):
        delete_sample_input(poc, UPLOADED_NAMES_FILE)
    assert uploaded_sample_inputs(poc) == ["own.txt"]


def test_a_file_removed_behind_the_api_is_not_reported_as_uploaded(poc):
    save_sample_input(poc, "own.txt", b"1")
    os.remove(os.path.join(poc, "sample_input", "own.txt"))

    assert uploaded_sample_inputs(poc) == []
