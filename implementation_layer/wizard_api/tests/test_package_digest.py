"""The package digest covers every module a run executes, and old records still compare.

A test run and Gate 3's approval are tied to a digest of the package. It covered
``run_poc.py``, the settings, the schema and ``prompts/``, and none of the package's
other modules (``pdf_report.py``, ``input_bundle.py``, a helper the agent added): an
edit to one left the digest as it was, Gate 3 stayed approved and the deployable
package was handed over with a change no run had tested.

The digest has a second formula that covers them. A digest stored before it is
compared in the formula it was made with, so a session approved or tested earlier
neither reopens nor locks because the formula changed.
"""

import hashlib
import os
import uuid

from helpers import requires_postgres, write_gate_artifacts
from wizard_api.routers import sessions as sessions_router
from wizard_api.schemas.session import SessionUpdate
from wizard_api.services import poc_service, session_service

_FIRST_FORMULA_FILES = (
    "run_poc.py",
    "config.yaml",
    "provider_config.py",
    "requirements.txt",
    "schemas/output_schema.py",
    "schemas/output_schema_requirements.json",
)


def _first_formula(poc: str) -> str:
    """The digest as it was computed before the second formula, written out again here.

    Not a call into the code under test: this is what the stored digests of
    existing sessions were made with, and it must keep giving the same value.
    """
    inner = hashlib.sha256()
    for name in _FIRST_FORMULA_FILES:
        inner.update(name.encode())
        path = os.path.join(poc, name)
        if os.path.isfile(path):
            with open(path, "rb") as fh:
                inner.update(fh.read())
    outer = hashlib.sha256(inner.hexdigest()[:16].encode())
    prompts = os.path.join(poc, "prompts")
    if os.path.isdir(prompts):
        for name in sorted(os.listdir(prompts)):
            outer.update(name.encode())
            with open(os.path.join(prompts, name), "rb") as fh:
                outer.update(fh.read())
    return outer.hexdigest()[:16]


def _write(poc: str, relative: str, content: str) -> None:
    path = os.path.join(poc, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def _package(poc: str) -> None:
    """A complete package with the modules the scaffolder and the agent put beside run_poc.py."""
    for relative, content in {
        "run_poc.py": "from gaik.software_components.extractor import Extractor\n",
        "requirements.txt": "gaik[extract]\n",
        "config.yaml": "stages: {}\n",
        "README.md": "# PoC\n",
        ".env.example": "AZURE_API_KEY=\n",
        "schemas/output_schema.json": "{}\n",
        "schemas/output_schema.py": "x = 1\n",
        "prompts/extract.md": "Extract the fields.\n",
        "pdf_report.py": "def render():\n    return 'report'\n",
        "input_bundle.py": "def bundle():\n    return []\n",
        "helpers/dates.py": "def parse(value):\n    return value\n",
        "app.py": "print('the test page')\n",
        "ui/server.py": "print('ui')\n",
        "evals/run_evals.py": "print('evals')\n",
        "sample_input/note.txt": "a note\n",
    }.items():
        _write(poc, relative, content)


# --- the two formulas -------------------------------------------------------------


def test_the_first_formula_gives_what_it_always_gave(tmp_path) -> None:
    poc = str(tmp_path / "poc")
    _package(poc)
    stored = _first_formula(poc)

    assert poc_service.package_digest(poc, like=stored) == stored
    assert len(stored) == 16 and not stored.startswith(poc_service.PACKAGE_DIGEST_V2)
    # It never covered the other modules, and still does not.
    _write(poc, "pdf_report.py", "def render():\n    return 'changed'\n")
    assert poc_service.package_digest(poc, like=stored) == stored
    # What it did cover, it still sees.
    _write(poc, "prompts/extract.md", "Extract other fields.\n")
    assert poc_service.package_digest(poc, like=stored) != stored
    assert poc_service.package_digest(poc, like=stored) == _first_formula(poc)


def test_a_new_digest_is_in_the_second_formula_and_says_so(tmp_path) -> None:
    poc = str(tmp_path / "poc")
    _package(poc)

    digest = poc_service.package_digest(poc)

    assert digest.startswith(poc_service.PACKAGE_DIGEST_V2)
    assert digest == poc_service.package_digest(poc, like=digest)
    assert digest == poc_service.package_digest(poc, like=None)
    assert digest == poc_service.package_digest(poc, like="")
    assert digest != poc_service.package_digest(poc, like=_first_formula(poc))


def test_the_modules_a_run_executes_change_the_digest_and_the_rest_do_not(tmp_path) -> None:
    poc = str(tmp_path / "poc")
    _package(poc)
    assert poc_service.runtime_modules(poc) == [
        "helpers/dates.py",
        "input_bundle.py",
        "pdf_report.py",
    ]

    def changes(relative: str, content: str = "# changed\n") -> bool:
        before, version = poc_service.package_digest(poc), poc_service.package_version(poc)
        _write(poc, relative, content)
        after = poc_service.package_digest(poc)
        # The preflight's version follows the code the same way (prompts aside).
        if not relative.startswith("prompts/"):
            assert (poc_service.package_version(poc) != version) == (after != before), relative
        assert poc_service.counts_for_package_digest(relative) == (after != before), relative
        return after != before

    for relative in (
        "run_poc.py",
        "config.yaml",
        "schemas/output_schema.py",
        "prompts/extract.md",
        "pdf_report.py",
        "input_bundle.py",
        "helpers/dates.py",
        "document_manifest.py",  # one that was not there before
    ):
        assert changes(relative), relative
    for relative in (
        "README.md",
        ".env.example",
        "app.py",
        "ui/server.py",
        "evals/run_evals.py",
        "sample_input/script.py",
        "output/result.py",
        "notes.txt",
    ):
        assert not changes(relative), relative


def test_a_linked_module_is_not_read_into_the_digest(tmp_path) -> None:
    poc = str(tmp_path / "poc")
    _package(poc)
    before = poc_service.package_digest(poc)
    outside = tmp_path / "outside.py"
    outside.write_text("secret = 1\n", encoding="utf-8")

    os.symlink(outside, os.path.join(poc, "linked.py"))

    assert poc_service.package_digest(poc) == before
    assert "linked.py" not in poc_service.runtime_modules(poc)


def test_a_record_is_brought_to_the_second_formula_only_while_it_still_holds(tmp_path) -> None:
    poc = str(tmp_path / "poc")
    _package(poc)
    stored = _first_formula(poc)

    assert poc_service.current_formula_digest(poc, stored) == poc_service.package_digest(poc)
    assert poc_service.current_formula_digest(poc, poc_service.package_digest(poc)) is None
    assert poc_service.current_formula_digest(poc, None) is None
    _write(poc, "run_poc.py", "print('changed since the record')\n")
    assert poc_service.current_formula_digest(poc, stored) is None


# --- sessions --------------------------------------------------------------------


def _file(client, sid: str, path: str):
    return client.get(f"/sessions/{sid}/poc/file", params={"path": path})


def _save(client, sid: str, path: str, content: str):
    digest = _file(client, sid, path).json()["digest"]
    return client.put(
        f"/sessions/{sid}/poc/file",
        params={"path": path},
        json={"content": content, "base_digest": digest},
    )


def _approved_session(client, db_session, user: str, *, first_formula: bool) -> dict:
    """A session past Gate 3 with a tested, approved package.

    With ``first_formula`` its three stored digests are what a session approved
    before the second formula holds.
    """
    created = client.post("/sessions", json={"user_id": user, "title": "Digest"}).json()
    sid = created["id"]
    write_gate_artifacts(created["output_dir"], "gate_3")
    poc = os.path.join(created["output_dir"], "poc")
    _package(poc)
    client.patch(f"/sessions/{sid}", json={"step": 4})
    client.patch(f"/sessions/{sid}", json={"gate_statuses": {"gate_1": "approved"}})
    client.patch(f"/sessions/{sid}", json={"step": 9})
    client.patch(f"/sessions/{sid}", json={"gate_statuses": {"gate_2": "approved"}})
    client.patch(f"/sessions/{sid}", json={"step": 10})
    session = session_service.get_session(db_session, uuid.UUID(sid))
    tested = _first_formula(poc) if first_formula else poc_service.package_digest(poc)
    session_service.update_session(
        db_session,
        session,
        SessionUpdate(
            metadata={
                "last_successful_run": "run-1",
                "agent_step": 10,
                session_service.RUN_PACKAGE_KEY: tested,
                session_service.SUCCESSFUL_RUN_PACKAGE_KEY: tested,
            }
        ),
    )
    client.patch(f"/sessions/{sid}", json={"step": 11})
    approved = client.patch(f"/sessions/{sid}", json={"gate_statuses": {"gate_3": "approved"}})
    assert approved.status_code == 200, approved.text
    client.patch(f"/sessions/{sid}", json={"step": 12})
    if first_formula:
        session = session_service.get_session(db_session, uuid.UUID(sid))
        content = dict(session.session_metadata[session_service.APPROVED_CONTENT_KEY])
        content["package"] = tested
        session_service.update_session(
            db_session,
            session,
            SessionUpdate(metadata={session_service.APPROVED_CONTENT_KEY: content}),
        )
    return created


def _metadata(client, sid: str) -> dict:
    return client.get(f"/sessions/{sid}").json()["metadata"]


@requires_postgres
def test_a_session_approved_before_the_second_formula_stays_approved_and_open(
    client, db_session
) -> None:
    created = _approved_session(client, db_session, "before", first_formula=True)
    sid = created["id"]
    stored = _metadata(client, sid)[session_service.SUCCESSFUL_RUN_PACKAGE_KEY]
    assert len(stored) == 16

    # What the PoC tab compares with the stored digest is in the same formula.
    assert client.get(f"/sessions/{sid}/poc/files").json()["package_digest"] == stored
    # What a chat turn runs when it ends: nothing changed, nothing reopens.
    session = session_service.get_session(db_session, uuid.UUID(sid))
    assert sessions_router._reopen_if_approved_content_changed(db_session, session) is False
    assert sessions_router._successful_run_is_of_another_package(session) is False
    detail = client.get(f"/sessions/{sid}").json()
    assert detail["gate_statuses"]["gate_3"] == "approved"
    assert "gate_reopened" not in detail["metadata"]
    assert client.get(f"/sessions/{sid}/poc/deployable").status_code == 200
    # Reading changed no record.
    assert _metadata(client, sid)[session_service.SUCCESSFUL_RUN_PACKAGE_KEY] == stored
    assert _metadata(client, sid)[session_service.APPROVED_CONTENT_KEY]["package"] == stored


@requires_postgres
def test_such_a_session_still_sees_a_change_to_what_its_digest_covered(client, db_session) -> None:
    created = _approved_session(client, db_session, "before-run-poc", first_formula=True)
    sid = created["id"]
    # The agent rewrites run_poc.py; no editor, no upgrade of the records.
    _write(os.path.join(created["output_dir"], "poc"), "run_poc.py", "print('rewritten')\n")

    session = session_service.get_session(db_session, uuid.UUID(sid))
    assert sessions_router._successful_run_is_of_another_package(session) is True
    assert sessions_router._reopen_if_approved_content_changed(db_session, session) is True
    assert client.get(f"/sessions/{sid}").json()["gate_statuses"]["gate_3"] == "pending"


@requires_postgres
def test_an_edit_outside_the_digest_brings_its_records_to_the_second_formula_and_keeps_all_open(
    client, db_session
) -> None:
    sid = _approved_session(client, db_session, "before-readme", first_formula=True)["id"]

    saved = _save(client, sid, "README.md", "# Edited\n")

    assert saved.status_code == 200 and saved.json()["gate_reopened"] is None
    metadata = _metadata(client, sid)
    for value in (
        metadata[session_service.SUCCESSFUL_RUN_PACKAGE_KEY],
        metadata[session_service.RUN_PACKAGE_KEY],
        metadata[session_service.APPROVED_CONTENT_KEY]["package"],
    ):
        assert value.startswith(poc_service.PACKAGE_DIGEST_V2)
    detail = client.get(f"/sessions/{sid}").json()
    assert detail["gate_statuses"]["gate_3"] == "approved"
    assert detail["metadata"]["last_successful_run"] == "run-1"
    listed = client.get(f"/sessions/{sid}/poc/files").json()["package_digest"]
    assert listed == metadata[session_service.SUCCESSFUL_RUN_PACKAGE_KEY]
    assert client.get(f"/sessions/{sid}/poc/deployable").status_code == 200


@requires_postgres
def test_an_edit_to_another_module_reopens_gate_3_in_an_old_session_too(client, db_session) -> None:
    sid = _approved_session(client, db_session, "before-helper", first_formula=True)["id"]
    assert _file(client, sid, "pdf_report.py").json()["affects_package"] is True

    saved = _save(client, sid, "pdf_report.py", "def render():\n    return 'edited'\n")

    assert saved.status_code == 200
    assert saved.json()["gate_reopened"] == "gate_3"
    detail = client.get(f"/sessions/{sid}").json()
    assert detail["gate_statuses"]["gate_3"] == "pending"
    assert client.get(f"/sessions/{sid}/poc/deployable").status_code == 409


@requires_postgres
def test_an_edit_to_another_module_reopens_gate_3(client, db_session) -> None:
    sid = _approved_session(client, db_session, "after-helper", first_formula=False)["id"]

    saved = _save(client, sid, "helpers/dates.py", "def parse(value):\n    return None\n")

    assert saved.json()["gate_reopened"] == "gate_3"
    assert client.get(f"/sessions/{sid}").json()["gate_statuses"]["gate_3"] == "pending"


@requires_postgres
def test_the_test_page_and_the_evals_are_not_what_a_run_tested(client, db_session) -> None:
    sid = _approved_session(client, db_session, "after-ui", first_formula=False)["id"]

    for path in ("app.py", "ui/server.py", "evals/run_evals.py"):
        assert _file(client, sid, path).json()["affects_package"] is False
        saved = _save(client, sid, path, "print('edited')\n")
        assert saved.status_code == 200 and saved.json()["gate_reopened"] is None

    assert client.get(f"/sessions/{sid}").json()["gate_statuses"]["gate_3"] == "approved"
    assert client.get(f"/sessions/{sid}/poc/deployable").status_code == 200


@requires_postgres
def test_before_gate_3_an_edit_to_another_module_closes_the_download(client, db_session) -> None:
    created = client.post("/sessions", json={"user_id": "tested", "title": "Digest"}).json()
    sid = created["id"]
    write_gate_artifacts(created["output_dir"], "gate_3")
    poc = os.path.join(created["output_dir"], "poc")
    _package(poc)
    session = session_service.get_session(db_session, uuid.UUID(sid))
    session_service.update_session(
        db_session,
        session,
        SessionUpdate(
            metadata={
                "last_successful_run": "run-1",
                session_service.SUCCESSFUL_RUN_PACKAGE_KEY: poc_service.package_digest(poc),
            }
        ),
    )
    assert client.get(f"/sessions/{sid}/poc/deployable").status_code == 200

    _save(client, sid, "input_bundle.py", "def bundle():\n    return ['edited']\n")

    refused = client.get(f"/sessions/{sid}/poc/deployable")
    assert refused.status_code == 409
    assert refused.json()["detail"]["error"] == "package_changed_since_run"
    listing = client.get(f"/sessions/{sid}/poc/files").json()
    assert (
        listing["package_digest"]
        != _metadata(client, sid)[session_service.SUCCESSFUL_RUN_PACKAGE_KEY]
    )
