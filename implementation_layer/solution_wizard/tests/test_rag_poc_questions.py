"""The RAG PoC answers its questions without a terminal.

The wizard's sandbox and a case run start ``python run_poc.py`` with no terminal.
The entrypoint waited for a typed question, read the end of input at once, and
ended with exit code 0 and an empty ``output/``: the test run showed as
succeeded with nothing to look at, and a case whose question was attached as a
text file failed with "wrote no result matching the output fields" (test
instance, 12 Nov 2026).

These run the scaffolded entrypoint as a subprocess against a stub ``gaik``, so
no model is called and gaik need not be installed.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint
from solution_wizard.scaffolder import scaffold_poc

EXAMPLES = Path(__file__).parent.parent / "examples"

_STUBS = {
    "gaik/__init__.py": "",
    "gaik/software_components/__init__.py": "",
    "gaik/software_components/llm/__init__.py": (
        "def get_llm_config(provider, **settings):\n"
        "    config = {'provider': provider, **settings}\n"
        "    config.setdefault('embedding_model', 'stub-embedding')\n"
        "    return config\n"
    ),
    "gaik/software_components/llm/providers.py": "def resolve_provider(name):\n    return name\n",
    "gaik/software_modules/__init__.py": "",
    # Says in the answer how many documents were indexed, so a test can tell that
    # a question file was not taken for a document.
    "gaik/software_modules/RAG_workflow.py": (
        "class _Result:\n"
        "    def __init__(self, answer):\n"
        "        self.answer = answer\n"
        "        self.documents = []\n"
        "\n"
        "\n"
        "class RAGWorkflow:\n"
        "    def __init__(self, **settings):\n"
        "        self.indexed = 0\n"
        "\n"
        "    def index_documents(self, documents):\n"
        "        self.indexed = len(documents)\n"
        "\n"
        "    def ask(self, query, stream=False):\n"
        "        return _Result(f'answer to {query!r} from {self.indexed} document(s)')\n"
    ),
}


@pytest.fixture
def poc(tmp_path):
    """A scaffolded RAG package with one document, and a stub gaik to run it on."""
    scaffold_poc(Blueprint.from_file(EXAMPLES / "rag_workflow_blueprint.json"), tmp_path)
    stubs = tmp_path / "stubs"
    for name, source in _STUBS.items():
        path = stubs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    poc_dir = tmp_path / "poc"
    sample = poc_dir / "sample_input"
    sample.mkdir(exist_ok=True)
    # The stub never opens it; the entrypoint only looks for the suffix.
    (sample / "guide.pdf").write_bytes(b"%PDF-1.4\n")
    return poc_dir


def _run(poc_dir: Path, *args: str, stdin: str = "") -> subprocess.CompletedProcess:
    """Run the entrypoint with no terminal: its input is a pipe, empty unless given.

    A pipe, not the null device, which Windows reports as a terminal.
    """
    env = {**os.environ, "PYTHONPATH": str(poc_dir.parent / "stubs"), "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, "run_poc.py", *args],
        cwd=poc_dir,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )


def _results(poc_dir: Path) -> list[dict]:
    return json.loads((poc_dir / "output" / "session_results.json").read_text(encoding="utf-8"))


def test_a_question_attached_as_a_text_file_is_answered(poc):
    (poc / "sample_input" / "kysymys.txt").write_text(
        "How do I enrol on a course?\n", encoding="utf-8"
    )

    done = _run(poc)

    assert done.returncode == 0, done.stderr
    assert _results(poc) == [
        {
            "query": "How do I enrol on a course?",
            "answer": "answer to 'How do I enrol on a course?' from 1 document(s)",
        }
    ]
    # The log names the file the questions came from.
    assert "1 question(s) from kysymys.txt" in done.stdout


def test_every_line_of_a_question_file_is_one_question(poc):
    (poc / "sample_input" / "questions.md").write_text(
        "\ufeffFirst question?\n\n  Second question?  \n", encoding="utf-8"
    )

    done = _run(poc)

    assert done.returncode == 0, done.stderr
    assert [r["query"] for r in _results(poc)] == ["First question?", "Second question?"]


def test_the_users_own_question_file_is_read_instead_of_the_sample(poc):
    sample = poc / "sample_input"
    (sample / "sample_questions.txt").write_text("The package's sample?\n", encoding="utf-8")
    (sample / "mine.txt").write_text("My own question?\n", encoding="utf-8")
    (sample / ".uploaded").write_text("guide.pdf\nmine.txt\n", encoding="utf-8")

    done = _run(poc)

    assert done.returncode == 0, done.stderr
    assert [r["query"] for r in _results(poc)] == ["My own question?"]


def test_questions_piped_to_the_run_come_before_the_question_files(poc):
    """A piped question was answered before question files existed, and still is."""
    (poc / "sample_input" / "sample_questions.txt").write_text(
        "The package's sample?\n", encoding="utf-8"
    )

    done = _run(poc, stdin="Piped question?\n")

    assert done.returncode == 0, done.stderr
    assert [r["query"] for r in _results(poc)] == ["Piped question?"]


def test_the_scaffolders_placeholder_text_is_not_asked_as_questions(poc):
    sample = poc / "sample_input"
    (sample / "question.txt").write_text("The real question?\n", encoding="utf-8")
    # What the scaffolder leaves when it cannot write a sample PDF.
    (sample / "synthetic_sample.txt").write_text(
        "SYNTHETIC SAMPLE\nNOTE: Replace with a real PDF document.\n", encoding="utf-8"
    )

    done = _run(poc)

    assert done.returncode == 0, done.stderr
    assert [r["query"] for r in _results(poc)] == ["The real question?"]


def test_a_question_file_in_a_subfolder_is_found_like_the_documents_are(poc):
    """A case's bundle keeps its inputs in subfolders of sample_input/."""
    folder = poc / "sample_input" / "poc_input"
    folder.mkdir()
    (folder / "questions.txt").write_text("From the bundle's folder?\n", encoding="utf-8")

    done = _run(poc)

    assert done.returncode == 0, done.stderr
    assert [r["query"] for r in _results(poc)] == ["From the bundle's folder?"]
    assert "from poc_input/questions.txt" in done.stdout


def test_a_run_with_no_question_fails_and_says_how_to_give_one(poc):
    done = _run(poc)

    # Not exit code 0 with an empty output/: that showed as a successful test run.
    assert done.returncode == 1
    assert "ERROR: No question to answer" in done.stderr
    assert "sample_input/" in done.stderr
    assert not (poc / "output" / "session_results.json").exists()


def test_a_long_text_file_is_refused_as_a_document_not_asked_line_by_line(poc):
    """A guide uploaded as text would otherwise cost one model call a line."""
    (poc / "sample_input" / "guide.md").write_text(
        "".join(f"Line {n} of the guide.\n" for n in range(200)), encoding="utf-8"
    )

    done = _run(poc)

    assert done.returncode == 1
    assert "ERROR: guide.md" in done.stderr
    assert "must be PDF" in done.stderr
    assert not (poc / "output" / "session_results.json").exists()


def test_a_single_question_on_the_command_line_still_works(poc):
    done = _run(poc, "--query", "From the command line?")

    assert done.returncode == 0, done.stderr
    result = json.loads((poc / "output" / "query_result.json").read_text(encoding="utf-8"))
    assert result["query"] == "From the command line?"


def test_the_synthetic_package_has_a_question_for_its_first_test_run(tmp_path):
    """The first test run of a new package has only the wizard's sample input."""
    scaffold_poc(
        Blueprint.from_file(EXAMPLES / "rag_workflow_blueprint.json"), tmp_path, synthetic=True
    )

    questions = tmp_path / "poc" / "sample_input" / "sample_questions.txt"

    assert [q for q in questions.read_text(encoding="utf-8").splitlines() if q.strip()]


def test_scaffolding_again_keeps_a_question_file_that_is_already_there(tmp_path):
    blueprint = Blueprint.from_file(EXAMPLES / "rag_workflow_blueprint.json")
    questions = tmp_path / "poc" / "sample_input" / "sample_questions.txt"
    questions.parent.mkdir(parents=True)
    questions.write_text("My own question?\n", encoding="utf-8")

    scaffold_poc(blueprint, tmp_path, synthetic=True)

    assert questions.read_text(encoding="utf-8") == "My own question?\n"
