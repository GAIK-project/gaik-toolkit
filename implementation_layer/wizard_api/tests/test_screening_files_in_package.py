"""The AI Act screening goes with the solution's files when the user asked for one.

SKILL.md Phase 12 offers an optional screening that writes ``ai_act_screening.json``
beside the blueprint and ``docs/ai_act_screening.md`` as its brief. The deployable
package says it holds both "with a screening". They are not among the documents
``generate_docs.py`` writes, so they are listed apart from them, and only when the
session has them as real files.
"""

import os

from wizard_api.services import poc_service


def _session(tmp_path, *, data=True, brief=True, docs=("user_guide",)):
    session = tmp_path / "session"
    (session / "docs").mkdir(parents=True)
    (session / "use_case.blueprint.json").write_text("{}")
    for name in docs:
        (session / "docs" / f"{name}.md").write_text("# doc")
    if data:
        (session / "ai_act_screening.json").write_text("{}")
    if brief:
        (session / "docs" / "ai_act_screening.md").write_text("# brief")
    return session


def _names(session):
    return [name for name, _ in poc_service.solution_files(str(session))]


def test_the_screening_and_its_brief_follow_the_documents(tmp_path) -> None:
    session = _session(tmp_path, docs=("user_guide", "evaluation_plan"))

    assert _names(session) == [
        "use_case.blueprint.json",
        "docs/user_guide.md",
        "docs/evaluation_plan.md",
        "ai_act_screening.json",
        "docs/ai_act_screening.md",
    ]


def test_a_session_that_never_ran_the_screening_lists_neither(tmp_path) -> None:
    session = _session(tmp_path, data=False, brief=False)

    assert _names(session) == ["use_case.blueprint.json", "docs/user_guide.md"]


def test_each_of_the_two_is_listed_on_its_own(tmp_path) -> None:
    assert _names(_session(tmp_path / "a", brief=False)) == [
        "use_case.blueprint.json",
        "docs/user_guide.md",
        "ai_act_screening.json",
    ]
    assert _names(_session(tmp_path / "b", data=False)) == [
        "use_case.blueprint.json",
        "docs/user_guide.md",
        "docs/ai_act_screening.md",
    ]


def test_the_screening_is_not_one_of_the_generated_documents() -> None:
    """test_poc_endpoints holds SOLUTION_DOC_NAMES equal to generate_docs.py's list."""
    assert "ai_act_screening" not in poc_service.SOLUTION_DOC_NAMES


def test_other_files_in_docs_still_stay_out(tmp_path) -> None:
    session = _session(tmp_path)
    for name in ("notes.md", ".env", "ai_act_screening_old.md", "ai_act_screening.json"):
        (session / "docs" / name).write_text("x")

    assert _names(session) == [
        "use_case.blueprint.json",
        "docs/user_guide.md",
        "ai_act_screening.json",
        "docs/ai_act_screening.md",
    ]


def test_a_linked_screening_file_is_not_followed(tmp_path) -> None:
    session = _session(tmp_path, data=False, brief=False)
    secret = tmp_path / "secret.txt"
    secret.write_text("not the session's")
    os.symlink(secret, session / "ai_act_screening.json")
    os.symlink(secret, session / "docs" / "ai_act_screening.md")

    assert _names(session) == ["use_case.blueprint.json", "docs/user_guide.md"]


def test_a_linked_documentation_folder_takes_the_brief_with_it(tmp_path) -> None:
    session = tmp_path / "session"
    session.mkdir()
    (session / "ai_act_screening.json").write_text("{}")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "ai_act_screening.md").write_text("not the session's")
    os.symlink(elsewhere, session / "docs")

    # The data file is the session's own; the brief is in a folder that is not.
    assert _names(session) == ["ai_act_screening.json"]


def test_an_oversized_screening_file_stays_out(tmp_path, monkeypatch) -> None:
    session = _session(tmp_path, data=False, brief=False)
    (session / "ai_act_screening.json").write_text("x" * 11)
    (session / "docs" / "ai_act_screening.md").write_text("x" * 5)
    monkeypatch.setattr(poc_service, "MAX_SOLUTION_FILE_BYTES", 10)

    assert _names(session) == [
        "use_case.blueprint.json",
        "docs/user_guide.md",
        "docs/ai_act_screening.md",
    ]


def test_the_package_lists_the_screening_by_the_names_it_has_in_it(tmp_path) -> None:
    session = _session(tmp_path)

    names = poc_service.solution_file_names(str(session), can_draw=True)

    assert names == [
        "use_case.blueprint.json",
        "workflow.bpmn",
        "docs/user_guide.md",
        "ai_act_screening.json",
        "docs/ai_act_screening.md",
    ]
