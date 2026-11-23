"""A package built on a gaik part whose heavy package loads only at run time.

RAGWorkflow parses with VisionRagParser by default, which needs docling. The
import of RAGWorkflow succeeds, so the package passed every check and then
failed on its first document (UC03, 5 Nov 2026). The sandbox image leaves
docling out on purpose; the check says so before a run. Since gaik 0.8.10
RAGWorkflow(parser="text") needs no docling, and that use is ready.
"""

import pytest
from wizard_api.services import poc_service
from wizard_api.services.poc_service import package_problems


def _package(tmp_path, entrypoint: str) -> str:
    poc = tmp_path / "poc"
    poc.mkdir()
    (poc / "run_poc.py").write_text(entrypoint)
    (poc / "requirements.txt").write_text("gaik[vector-store]\n")
    (poc / "README.md").write_text("# PoC\n")
    return str(poc)


@pytest.fixture
def image_without_docling(monkeypatch):
    """gaik is there, docling is not: the runner image as it is built."""
    monkeypatch.setattr(poc_service, "_gaik_available", lambda: True)
    monkeypatch.setattr(
        poc_service, "_resolvable", lambda module: module.split(".")[0] != "docling"
    )


@pytest.mark.parametrize(
    "line",
    [
        "from gaik.software_modules.RAG_workflow import RAGWorkflow",
        "from gaik.software_modules.RAG_workflow.pipeline import RAGWorkflow",
        "from gaik.software_modules import RAGWorkflow",
    ],
)
def test_rag_workflow_without_docling_is_refused_before_the_run(
    tmp_path, image_without_docling, line
):
    problems = package_problems(_package(tmp_path, f"import json\n{line}\n"))

    assert len(problems) == 1
    assert problems[0].startswith("run_poc.py line 2 uses ")
    assert "needs docling (gaik extra rag-parser-vision)" in problems[0]
    assert "PyMuPDFParser" in problems[0]


def test_a_docling_parser_imported_directly_is_refused(tmp_path, image_without_docling):
    source = "from gaik.software_components.RAG.rag_parser_docling import DoclingRagParser\n"

    [problem] = package_problems(_package(tmp_path, source))

    assert "uses DoclingRagParser" in problem
    assert "gaik extra rag-parser-docling" in problem


def test_rag_components_without_the_vision_parser_are_ready(tmp_path, image_without_docling):
    source = (
        "from gaik.software_components.parsers import PyMuPDFParser\n"
        "from gaik.software_components.RAG.embedder import Embedder\n"
    )

    assert package_problems(_package(tmp_path, source)) == []


def test_with_docling_in_the_image_rag_workflow_is_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(poc_service, "_gaik_available", lambda: True)
    monkeypatch.setattr(poc_service, "_resolvable", lambda module: True)
    source = "from gaik.software_modules.RAG_workflow import RAGWorkflow\n"

    assert package_problems(_package(tmp_path, source)) == []


def test_a_guarded_optional_import_is_still_checked_for_its_run_time_needs(
    tmp_path, image_without_docling
):
    """A try/except ImportError hides a missing module, but RAGWorkflow imports
    fine; the failure comes later, inside the run, where no except catches it."""
    source = (
        "from gaik.software_components.parsers import PyMuPDFParser\n"
        "try:\n"
        "    from gaik.software_modules.RAG_workflow import RAGWorkflow\n"
        "except ImportError:\n"
        "    RAGWorkflow = None\n"
    )

    [problem] = package_problems(_package(tmp_path, source))

    assert "uses RAGWorkflow" in problem


_TEXT_RAG = (
    "from gaik.software_modules.RAG_workflow import RAGWorkflow\n"
    "workflow = RAGWorkflow(api_config={{}}, {parser})\n"
)


def test_rag_workflow_on_the_text_layer_is_ready(tmp_path, image_without_docling):
    source = _TEXT_RAG.format(parser='parser="text"')

    assert package_problems(_package(tmp_path, source)) == []


@pytest.mark.parametrize(
    "parser",
    ['parser="vision"', "parser=parser_kind", "persist=True"],
    ids=["vision", "read from a variable", "left at its default"],
)
def test_rag_workflow_that_may_parse_with_vision_is_refused(
    tmp_path, image_without_docling, parser
):
    [problem] = package_problems(_package(tmp_path, _TEXT_RAG.format(parser=parser)))

    assert "uses RAGWorkflow" in problem
    assert 'pass parser="text" to RAGWorkflow' in problem


def test_one_vision_workflow_beside_a_text_one_is_refused(tmp_path, image_without_docling):
    source = _TEXT_RAG.format(parser='parser="text"') + "other = RAGWorkflow(api_config={})\n"

    [problem] = package_problems(_package(tmp_path, source))

    assert "uses RAGWorkflow" in problem
