"""Only the session's own regular files are listed, zipped or packaged.

A symlink in the session directory, to a file or a folder, is skipped wherever
the API lists, zips or reads the package.
"""

import os

from wizard_api.services import poc_service


def _tree(tmp_path):
    poc = tmp_path / "poc"
    (poc / "schemas").mkdir(parents=True)
    (poc / "run_poc.py").write_text("print('hi')\n")
    (poc / "schemas" / "output_schema.py").write_text("x = 1\n")
    outside_file = tmp_path / "outside" / "notes.txt"
    outside_file.parent.mkdir()
    outside_file.write_text("not part of the package")
    os.symlink(outside_file, poc / "linked.txt")
    os.symlink(outside_file.parent, poc / "linked_dir")
    os.symlink(poc / "run_poc.py", poc / "inner_link.py")  # even one pointing inside
    return poc, outside_file


def test_listing_skips_symlinked_files_and_folders(tmp_path) -> None:
    poc, _ = _tree(tmp_path)

    assert poc_service.regular_files(poc) == ["run_poc.py", "schemas/output_schema.py"]


def test_a_symlink_is_not_a_regular_file(tmp_path) -> None:
    poc, outside_file = _tree(tmp_path)

    assert poc_service.regular_file(poc / "run_poc.py", poc)
    assert not poc_service.regular_file(poc / "linked.txt", poc)
    assert not poc_service.regular_file(outside_file, poc)  # outside the root
    assert not poc_service.regular_file(poc / "linked_dir" / "notes.txt", poc)


def test_deployable_files_leave_symlinks_out(tmp_path) -> None:
    poc, _ = _tree(tmp_path)

    assert "linked.txt" not in poc_service.deployable_files(str(poc))
    assert not any(f.startswith("linked_dir") for f in poc_service.deployable_files(str(poc)))


def test_the_solutions_files_leave_symlinks_out(tmp_path) -> None:
    """The blueprint, the diagrams and the documentation go into the deployable
    package from beside poc/: a link there must not pull another file in."""
    session = tmp_path / "session"
    (session / "docs").mkdir(parents=True)
    (session / "ui_view").mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("not the session's")
    (session / "use_case.blueprint.json").write_text("{}")
    (session / "docs" / "user_guide.md").write_text("# guide")
    os.symlink(secret, session / "workflow.mmd")
    # A document the wizard writes, by name, but a link.
    os.symlink(secret, session / "docs" / "technical_specification.md")
    os.symlink(secret, session / "ui_view" / "workflow.bpmn")
    (session / "workflow.bpmn").write_text("<definitions/>")

    found = dict(poc_service.solution_files(str(session)))

    assert sorted(found) == ["docs/user_guide.md", "use_case.blueprint.json"]
    assert all(os.path.realpath(path) != os.path.realpath(secret) for path in found.values())
    # The diagram kept for when the blueprint cannot be drawn: the linked
    # workspace diagram is passed over for the agent's own, a real file.
    assert poc_service.stored_bpmn(str(session)) == (
        os.path.join(os.path.realpath(session), "workflow.bpmn"),
        "agent_draft",
    )


def test_only_the_documents_the_wizard_writes_and_of_a_sane_size(tmp_path, monkeypatch) -> None:
    """docs/ is the agent's folder: only generate_docs.py's documents are handed over."""
    session = tmp_path / "session"
    (session / "docs" / "__pycache__").mkdir(parents=True)
    for name in ("user_guide.md", "evaluation_plan.md", ".env", "invoice.pdf", "notes.md"):
        (session / "docs" / name).write_text("x")
    (session / "docs" / "__pycache__" / "a.pyc").write_text("x")
    (session / "docs" / "developer_guide.md").write_text("x" * 11)
    monkeypatch.setattr(poc_service, "MAX_SOLUTION_FILE_BYTES", 10)

    found = [name for name, _ in poc_service.solution_files(str(session))]

    # In the generator's order; the oversized guide stays out.
    assert found == ["docs/user_guide.md", "docs/evaluation_plan.md"]


def test_a_linked_documentation_folder_is_not_read(tmp_path) -> None:
    session = tmp_path / "session"
    session.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "user_guide.md").write_text("not the session's")
    os.symlink(elsewhere, session / "docs")

    assert poc_service.solution_files(str(session)) == []
    assert poc_service.stored_bpmn(str(session)) is None
    assert poc_service.stored_bpmn(None) is None
    assert poc_service.solution_files(None) == []
    assert poc_service.solution_files(str(tmp_path / "missing")) == []


def test_package_checks_do_not_read_through_a_symlink(tmp_path) -> None:
    poc, outside_file = _tree(tmp_path)
    (poc / "run_poc.py").unlink()
    os.symlink(outside_file, poc / "run_poc.py")

    assert "run_poc.py is missing" in poc_service.package_problems(str(poc))


def test_a_saved_run_is_not_read_through_a_linked_folder(tmp_path) -> None:
    from wizard_api.services import run_context

    session = tmp_path / "session"
    session.mkdir()
    elsewhere = tmp_path / "elsewhere" / "run-1"
    (elsewhere / "output").mkdir(parents=True)
    (elsewhere / "run.json").write_text('{"run_id": "run-1"}')
    (elsewhere / "output" / "result.json").write_text("{}")
    os.symlink(tmp_path / "elsewhere", session / "runs")  # runs/ itself is the link

    assert run_context.saved(str(session), "run-1") is None
    assert run_context.saved_output(str(session), "run-1") is None


def test_a_saved_run_skips_a_linked_output_folder(tmp_path) -> None:
    from wizard_api.services import run_context

    session = tmp_path / "session"
    run = session / "runs" / "run-1"
    run.mkdir(parents=True)
    (run / "run.json").write_text('{"run_id": "run-1"}')
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "result.json").write_text("{}")
    os.symlink(outside, run / "output")

    assert run_context.saved_output(str(session), "run-1") == ({}, {})


def test_an_input_is_not_removed_through_a_linked_input_folder(tmp_path) -> None:
    poc = tmp_path / "poc"
    poc.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "a.pdf").write_bytes(b"%PDF")
    os.symlink(outside, poc / poc_service.SAMPLE_INPUT_DIR)

    assert poc_service.delete_sample_input(str(poc), "a.pdf") is False
    assert (outside / "a.pdf").exists()
