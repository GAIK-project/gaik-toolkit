"""Unit tests for the agentic (V2) path of the multi_source_report_generator.

All tests run without external API calls: the LLM client is faked by
monkeypatching ``pipeline.create_llm_client``. The fake exposes both ``chat``
(writer / curator) and ``chat_parsed`` (diff-editor reviewer).
"""

from __future__ import annotations

import pytest

pytest.importorskip("langgraph")

from gaik.software_modules.multi_source_report_generator import (  # noqa: E402
    MultiSourceReportGenerator,
)
from gaik.software_modules.multi_source_report_generator import pipeline as msrg  # noqa: E402
from gaik.software_modules.multi_source_report_generator.agentic.reviewer import (  # noqa: E402
    Correction,
    CorrectionList,
)

# ---------------------------------------------------------------------------
# Fake LLM client (content-driven so it is robust to parallel section order)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.model = "fake"
        self.provider = "fake"
        self.usage = {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}


def _title_of(user_prompt: str) -> str:
    for line in user_prompt.splitlines():
        if line.startswith("Report section to write:"):
            return line.split(":", 1)[1].strip()
    return "Section"


class _FakeClient:
    """A controllable fake.

    ``review_mode``:
      - "none"     -> reviewer proposes no corrections
      - "apply"    -> reviewer replaces "blue" with "green" (applies cleanly)
      - "fail"     -> reviewer proposes an unmatchable edit (stays unresolved)
    """

    def __init__(self, *, review_mode: str = "none"):
        self.review_mode = review_mode
        self.draft_calls: list[str] = []  # user prompts to draft_writer
        self.curation_calls: list[str] = []  # user prompts to curator
        self.parsed_calls: list[str] = []  # user prompts to chat_parsed

    def chat(self, messages, **kwargs):
        system = messages[0]["content"]
        user = messages[-1]["content"]
        if system.startswith("You are a research assistant"):
            self.curation_calls.append(user)
            return _FakeResponse("CURATED_BRIEF: only the relevant facts. The sky is blue.")
        self.draft_calls.append(user)
        title = _title_of(user)
        return _FakeResponse(f"Draft body for {title}. The sky is blue.")

    def chat_parsed(self, messages, response_format, **kwargs):
        user = messages[-1]["content"]
        self.parsed_calls.append(user)
        is_retry = "could not be applied" in user
        if is_retry:
            return CorrectionList(corrections=[], explanation="no more")
        if self.review_mode == "apply":
            return CorrectionList(
                corrections=[Correction(search="blue", replace="green", reason="fix color")]
            )
        if self.review_mode == "fail":
            return CorrectionList(
                corrections=[
                    Correction(
                        search="UNMATCHABLE_PASSAGE_THAT_IS_NOT_IN_THE_DRAFT_0123456789",
                        replace="x",
                        reason="cannot apply",
                    )
                ]
            )
        return CorrectionList(corrections=[], explanation="ok")


def _gen() -> MultiSourceReportGenerator:
    return MultiSourceReportGenerator(api_config={"use_azure": False, "api_key": "x", "model": "m"})


@pytest.fixture
def patch_llm(monkeypatch):
    def _install(client: _FakeClient) -> _FakeClient:
        monkeypatch.setattr(msrg, "create_llm_client", lambda cfg: client)
        return client

    return _install


SECTIONS = [
    {"title": "Background", "instructions": "Describe the context."},
    {"title": "Findings", "instructions": "List the findings."},
    {"title": "Recommendations", "instructions": "Give recommendations."},
]


# ---------------------------------------------------------------------------
# Sample-section split / match (pure helpers)
# ---------------------------------------------------------------------------


def test_split_sample_sections_top_level_only():
    sample = "# My Report\n## Background\nIntro prose.\n### Sub A\ndetail\n## Findings\n- a\n- b\n"
    sections = msrg._split_sample_sections(sample)
    assert set(sections) == {"background", "findings"}
    # Subsections stay inside their parent block (no fragmentation).
    bg_heading, bg_body = sections["background"]
    assert bg_heading == "Background"
    assert "### Sub A" in bg_body
    assert "## Findings" not in bg_body


def test_match_sample_section_exact_and_normalized():
    sample = "## 1. Background\nbody1\n## Recommendations & Next Steps\nbody2\n"
    sections = msrg._split_sample_sections(sample)
    # normalized: leading numbering stripped
    assert msrg._match_sample_section("Background", sections) is not None
    # exact original heading still works
    assert "body2" in (msrg._match_sample_section("Recommendations & Next Steps", sections) or "")
    # no match
    assert msrg._match_sample_section("Glossary", sections) is None


# ---------------------------------------------------------------------------
# End-to-end agentic run
# ---------------------------------------------------------------------------


def test_agentic_one_draft_per_section_and_order(tmp_path, patch_llm):
    client = patch_llm(_FakeClient(review_mode="none"))
    (tmp_path / "src.txt").write_text("Important fact: the sky is blue.", encoding="utf-8")
    out = tmp_path / "out"

    result = _gen().run(
        input_paths=[tmp_path / "src.txt"],
        sections=SECTIONS,
        report_title="My Report",
        output_dir=out,
        agentic=True,
    )

    # one writer draft per section
    assert len(client.draft_calls) == 3
    # no curation calls by default
    assert client.curation_calls == []
    # report assembled in the user's section order
    assert [s.title for s in result.sections] == ["Background", "Findings", "Recommendations"]
    assert result.markdown.index("## Background") < result.markdown.index("## Findings")
    # files written
    assert (out / "report.md").exists()
    assert (out / "sections" / "01_background.md").exists()


def test_agentic_reviewer_applies_corrections_before_assembly(tmp_path, patch_llm):
    client = patch_llm(_FakeClient(review_mode="apply"))
    (tmp_path / "src.txt").write_text("The sky is blue.", encoding="utf-8")

    result = _gen().run(
        input_paths=[tmp_path / "src.txt"],
        sections=[{"title": "Findings", "instructions": "Describe the sky."}],
        report_title="R",
        agentic=True,
    )
    # reviewer ran (chat_parsed called) and its edit was applied before assembly
    assert client.parsed_calls
    assert "green" in result.markdown
    assert "blue" not in result.sections[0].content_markdown


def test_agentic_review_options_none_reuses_writer(tmp_path, patch_llm):
    client = patch_llm(_FakeClient(review_mode="none"))
    (tmp_path / "src.txt").write_text("x", encoding="utf-8")
    # With review_options=None the same fake serves both chat and chat_parsed.
    _gen().run(
        input_paths=[tmp_path / "src.txt"],
        sections=[{"title": "A", "instructions": "a"}],
        agentic=True,
    )
    assert client.draft_calls and client.parsed_calls


def test_agentic_curation_one_brief_per_section_and_artifacts(tmp_path, patch_llm):
    client = patch_llm(_FakeClient(review_mode="none"))
    (tmp_path / "src.txt").write_text("The sky is blue.", encoding="utf-8")
    out = tmp_path / "out"

    _gen().run(
        input_paths=[tmp_path / "src.txt"],
        sections=SECTIONS,
        output_dir=out,
        agentic=True,
        curate_evidence=True,
    )
    # one curation call per section, and the draft used the curated brief
    assert len(client.curation_calls) == 3
    assert all("CURATED_BRIEF" in prompt for prompt in client.draft_calls)
    # briefs saved as artifacts
    assert (out / "evidence" / "curated_sections" / "background.md").exists()
    assert (out / "evidence" / "curated_sections" / "findings.md").exists()


def test_agentic_curation_no_output_dir_keeps_in_memory(tmp_path, patch_llm):
    client = patch_llm(_FakeClient(review_mode="none"))
    (tmp_path / "src.txt").write_text("The sky is blue.", encoding="utf-8")

    _gen().run(
        input_paths=[tmp_path / "src.txt"],
        sections=[{"title": "A", "instructions": "a"}],
        agentic=True,
        curate_evidence=True,
    )
    assert len(client.curation_calls) == 1
    # no output_dir -> nothing written under tmp_path
    assert not any(p.name == "curated_sections" for p in tmp_path.rglob("*"))


def test_agentic_strict_review_ignores_sample_match_warnings(tmp_path, patch_llm):
    """strict_review must NOT raise for informational 'no matching sample' warnings."""
    patch_llm(_FakeClient(review_mode="none"))
    (tmp_path / "src.txt").write_text("The sky is blue.", encoding="utf-8")
    sample = tmp_path / "sample.md"
    sample.write_text("# Example\n## Totally Different\nprose.\n", encoding="utf-8")
    out = tmp_path / "out"

    # Sample has no matching sections -> informational warnings, but strict_review
    # should NOT raise because no reviewer edits failed.
    result = _gen().run(
        input_paths=[tmp_path / "src.txt"],
        sections=[{"title": "Findings", "instructions": "a"}],
        output_dir=out,
        sample_report_path=sample,
        agentic=True,
        strict_review=True,  # must not raise here
    )
    assert (out / "report.md").exists()
    assert any("No matching sample section" in w for w in result.sections[0].revision_warnings)


def test_agentic_strict_review_raises_before_writing(tmp_path, patch_llm):
    patch_llm(_FakeClient(review_mode="fail"))
    (tmp_path / "src.txt").write_text("The sky is blue.", encoding="utf-8")
    out = tmp_path / "out"

    with pytest.raises(RuntimeError):
        _gen().run(
            input_paths=[tmp_path / "src.txt"],
            sections=[{"title": "A", "instructions": "a"}],
            output_dir=out,
            agentic=True,
            strict_review=True,
        )
    # no final report persisted
    assert not (out / "report.md").exists()


def test_agentic_warnings_returned_by_default(tmp_path, patch_llm):
    patch_llm(_FakeClient(review_mode="fail"))
    (tmp_path / "src.txt").write_text("The sky is blue.", encoding="utf-8")

    result = _gen().run(
        input_paths=[tmp_path / "src.txt"],
        sections=[{"title": "A", "instructions": "a"}],
        agentic=True,  # strict_review defaults to False
    )
    assert result.sections[0].revision_warnings  # unresolved edit -> warning


def test_agentic_polish_runs_after_review_and_adds_no_content(tmp_path, patch_llm):
    patch_llm(_FakeClient(review_mode="none"))
    (tmp_path / "src.txt").write_text("The sky is blue.", encoding="utf-8")
    events: list[str] = []

    result = _gen().run(
        input_paths=[tmp_path / "src.txt"],
        sections=[{"title": "Findings", "instructions": "Describe the sky."}],
        agentic=True,
        polish=True,
        progress_callback=events.append,
    )
    # polish event comes after the reviewer event for the section
    reviewer_idx = next(i for i, e in enumerate(events) if e.startswith("[Findings] reviewer:"))
    polish_idx = next(i for i, e in enumerate(events) if "style polish applied" in e)
    assert reviewer_idx < polish_idx
    # polish (empty corrections) introduced no new content
    assert "Draft body for Findings" in result.sections[0].content_markdown


def test_agentic_no_matching_sample_warns_and_uses_generic(tmp_path, patch_llm):
    client = patch_llm(_FakeClient(review_mode="none"))
    (tmp_path / "src.txt").write_text("The sky is blue.", encoding="utf-8")
    sample = tmp_path / "sample.md"
    sample.write_text("# Example\n## Totally Different\nprose.\n", encoding="utf-8")

    result = _gen().run(
        input_paths=[tmp_path / "src.txt"],
        sections=[{"title": "Findings", "instructions": "Describe the sky."}],
        sample_report_path=sample,
        agentic=True,
    )
    warnings = result.sections[0].revision_warnings
    assert any("No matching sample section" in w for w in warnings)
    # draft was told no format reference is available (generic path)
    assert any("No format reference is available" in p for p in client.draft_calls)


def test_agentic_matched_sample_passed_to_writer(tmp_path, patch_llm):
    client = patch_llm(_FakeClient(review_mode="none"))
    (tmp_path / "src.txt").write_text("The sky is blue.", encoding="utf-8")
    sample = tmp_path / "sample.md"
    sample.write_text("# Example\n## Findings\n- bullet one\n- bullet two\n", encoding="utf-8")

    result = _gen().run(
        input_paths=[tmp_path / "src.txt"],
        sections=[{"title": "Findings", "instructions": "Describe the sky."}],
        sample_report_path=sample,
        agentic=True,
    )
    # matched -> FORMAT REFERENCE with the sample block reaches the writer; no warning
    assert any("FORMAT REFERENCE" in p and "bullet one" in p for p in client.draft_calls)
    assert not any("No matching sample section" in w for w in result.sections[0].revision_warnings)


def test_agentic_progress_callback_receives_handovers(tmp_path, patch_llm):
    patch_llm(_FakeClient(review_mode="none"))
    (tmp_path / "src.txt").write_text("x", encoding="utf-8")
    events: list[str] = []

    _gen().run(
        input_paths=[tmp_path / "src.txt"],
        sections=[{"title": "Findings", "instructions": "a"}],
        agentic=True,
        progress_callback=events.append,
    )
    joined = "\n".join(events)
    assert "Writing 1 section(s) in parallel" in joined
    assert "[Findings] evidence loaded" in joined
    assert "[Findings] draft written" in joined
    assert "Assembling report in requested order" in joined


def test_langgraph_missing_raises_or_skip():
    try:
        import langgraph  # noqa: F401
    except ImportError:  # pragma: no cover
        with pytest.raises(ImportError):
            from gaik.software_modules.multi_source_report_generator.agentic import (  # noqa: F401
                run_agentic_report,
            )
    else:
        pytest.skip("langgraph is installed; import-error path not exercised")
