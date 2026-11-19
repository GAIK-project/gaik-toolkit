"""PDF ligatures read as letters, and missing-data markers kept inside a sentence."""

from types import SimpleNamespace

from gaik.software_components._ligatures import expand_ligatures
from gaik.software_components.knowledge_curator.models import SectionSpec
from gaik.software_components.report_synthesizer.prompts import (
    build_review_checks,
    writer_system_prompt,
)
from gaik.software_components.source_tracing.matching import find_run, tokens


def test_latin_ligatures_become_their_letters():
    assert expand_ligatures("Soﬁa, scaﬀolding, ﬂoor, oﬃce") == ("Sofia, scaffolding, floor, office")
    # Only the ligature block changes: superscripts and fractions stay as they are.
    assert expand_ligatures("m² ½") == "m² ½"


def test_a_quote_without_ligatures_matches_a_pdf_word_with_one():
    assert find_run(tokens("Tenant: Soﬁa Virtanen"), tokens("Sofia Virtanen")) == 1
    assert find_run(tokens("Tenant: Sofia Virtanen"), tokens("Soﬁa Virtanen")) == 1


def test_pymupdf_parser_returns_letters_for_ligatures(monkeypatch, tmp_path):
    from gaik.software_components.parsers import pymypdf

    page = SimpleNamespace(get_text=lambda *args, **kwargs: "Conﬁrm the rooﬁng")

    class Doc:
        is_pdf = True
        page_count = 1

        def __getitem__(self, index):
            return page

        def close(self):
            pass

    monkeypatch.setattr(pymypdf.fitz, "open", lambda *args, **kwargs: Doc())
    path = tmp_path / "minutes.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    assert pymypdf.PyMuPDFParser().parse_pdf(str(path)) == "Confirm the roofing"


def test_writer_and_reviewer_keep_a_missing_marker_in_a_sentence():
    rule = "inside a sentence that names"
    for citations in (True, False):
        assert rule in " ".join(writer_system_prompt(citations).split())
    section = SectionSpec(id="structures", title="Structures", instructions="Cover the floor.")
    assert rule in " ".join(build_review_checks(section, "").split())
