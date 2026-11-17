"""The editor and the deployable download on the package digest (``package_version``).

The digest covers every file of the package but its README files
(``poc_service._in_version``, tests in ``test_package_version.py``), and an
approval recorded under an older scheme is re-based on the package as it is
(``package_scheme``, ``test_gate_reopen.py``). These are about what the editor and
the download make of that:

- the editor tells, by a file's name, whether saving it changes the digest, and that
  must agree with the digest itself;
- a save in the editor reopens Gate 3 for a change to any file but a README, also in
  a session whose approval is of an older scheme: the re-basing must not take the
  edit into the approval;
- a session approved before the scheme changed keeps its approval and its download.
"""

import hashlib
import os
import uuid

import pytest
from helpers import requires_postgres, write_gate_artifacts
from wizard_api.routers import sessions as sessions_router
from wizard_api.schemas.session import SessionUpdate
from wizard_api.services import poc_service, session_service


@pytest.fixture(autouse=True)
def _runs_use_their_own_key(monkeypatch):
    """The editor saves code only while the test runs use a runner key of their own
    (``test_poc_file_editor.py`` covers the shared key); these tests edit modules."""
    monkeypatch.setenv("WIZARD_POC_RUNNER_SECRET", "wizard-v2-poc-run-keys")


_PACKAGE = {
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
    "ui/index.html": "<p>test page</p>\n",
    "evals/run_evals.py": "print('evals')\n",
    "labels.json": '["invoice", "receipt"]\n',
    "templates/report.md": "# The report\n",
    "sample_input/note.txt": "a note\n",
}


def _write(poc: str, relative: str, content: str) -> None:
    path = os.path.join(poc, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def _package(poc: str) -> None:
    for relative, content in _PACKAGE.items():
        _write(poc, relative, content)
    # The test page is the scaffolder's template as it is: package_problems reports a
    # changed copy (#220), and the download waits for a package without problems.
    templates_dir = getattr(poc_service, "_TEMPLATES_DIR", None)
    for relative, template in getattr(poc_service, "_TEST_PAGE_TEMPLATES", {}).items():
        if templates_dir is not None:
            _write(poc, relative, (templates_dir / template).read_text("utf-8"))


_FIXED_LIST = (
    "run_poc.py",
    "config.yaml",
    "provider_config.py",
    "requirements.txt",
    "schemas/output_schema.py",
    "schemas/output_schema_requirements.json",
)


def _with_prompts(inner, poc: str) -> str:
    outer = hashlib.sha256(inner.hexdigest()[:16].encode())
    prompts = os.path.join(poc, "prompts")
    for name in sorted(os.listdir(prompts)):
        outer.update(name.encode())
        with open(os.path.join(prompts, name), "rb") as fh:
            outer.update(fh.read())
    return outer.hexdigest()[:16]


def _older_scheme_digest(poc: str) -> str:
    """The digest as scheme 1 made it: a fixed list of files, and the prompts.

    Written out here, not taken from the code: it is what sessions approved and
    tested before the scheme changed have stored.
    """
    inner = hashlib.sha256()
    for name in _FIXED_LIST:
        inner.update(name.encode())
        path = os.path.join(poc, name)
        if os.path.isfile(path):
            with open(path, "rb") as fh:
                inner.update(fh.read())
    return _with_prompts(inner, poc)


def _scheme_2_digest(poc: str) -> str:
    """The digest as scheme 2 made it: the fixed list, every Python file and every file in
    ``schemas/``, and the prompts. Written out here, as ``_older_scheme_digest`` is."""
    names = set(_FIXED_LIST)
    for folder, dirs, files in os.walk(poc):
        rel = os.path.relpath(folder, poc)
        dirs[:] = sorted(
            d
            for d in dirs
            if not d.startswith(".")
            and d != "__pycache__"
            and not (rel == "." and d in {"sample_input", "output"})
        )
        for name in files:
            relpath = os.path.normpath(os.path.join(rel, name)).replace(os.sep, "/")
            if name.endswith(".py") or relpath.split("/", 1)[0] == "schemas":
                names.add(relpath)
    inner = hashlib.sha256()
    for name in sorted(n.replace("/", os.sep) for n in names):
        inner.update(name.encode())
        path = os.path.join(poc, name)
        if os.path.isfile(path):
            with open(path, "rb") as fh:
                inner.update(fh.read())
    return _with_prompts(inner, poc)


# --- what the editor says of a file agrees with the digest -------------------------


@pytest.mark.parametrize(
    ("relative", "counts"),
    [
        ("run_poc.py", True),
        ("config.yaml", True),
        ("requirements.txt", True),
        ("schemas/output_schema.py", True),
        ("schemas/output_schema.json", True),
        ("prompts/extract.md", True),
        ("pdf_report.py", True),
        ("input_bundle.py", True),
        ("helpers/dates.py", True),
        ("document_manifest.py", True),  # one that was not there before
        # Python of the test page and the evaluations is Python of the package.
        ("app.py", True),
        ("evals/run_evals.py", True),
        # Every other file of the package too: run_poc.py may read any of them.
        ("labels.json", True),
        (".env.example", True),
        ("notes.txt", True),
        ("templates/report.md", True),
        ("prompts/README.md", True),  # a prompt, whatever its name
        # Documentation for people, which no run reads.
        ("README.md", False),
        ("helpers/Readme.md", False),
        # The test page's folder: the page runs where the package is taken, no run reads it.
        ("ui/index.html", False),
        ("ui/solution.json", False),
        ("ui/server.py", False),
        # Not part of the package.
        ("AI-GENERATED.json", False),
        (".env", False),
        ("sample_input/script.py", False),
        ("output/result.py", False),
        (".cache/tool.py", False),
        ("helpers/__pycache__/dates.py", False),
    ],
)
def test_a_files_name_says_whether_saving_it_changes_the_digest(tmp_path, relative, counts) -> None:
    poc = str(tmp_path / "poc")
    _package(poc)
    before = sessions_router._approved_package_digest(poc)

    _write(poc, relative, "# changed\n")

    assert (sessions_router._approved_package_digest(poc) != before) is counts
    assert poc_service.counts_for_package_digest(relative) is counts


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


def _approved_session(client, db_session, user: str, *, older_scheme: bool) -> dict:
    """A session past Gate 3 with a tested, approved package.

    With ``older_scheme`` its stored digests and its approval are what a session
    approved before the digest covered every module holds: the older digest, and
    no ``package_scheme``.
    """
    # A user id is not a path: the tests name sessions after the file they edit.
    user = user.replace("/", "-")
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
    now = sessions_router._approved_package_digest(poc)
    session_service.update_session(
        db_session,
        session,
        SessionUpdate(
            metadata={
                "last_successful_run": "run-1",
                "agent_step": 10,
                session_service.RUN_PACKAGE_KEY: now,
                session_service.SUCCESSFUL_RUN_PACKAGE_KEY: now,
            }
        ),
    )
    client.patch(f"/sessions/{sid}", json={"step": 11})
    approved = client.patch(f"/sessions/{sid}", json={"gate_statuses": {"gate_3": "approved"}})
    assert approved.status_code == 200, approved.text
    client.patch(f"/sessions/{sid}", json={"step": 12})
    if older_scheme:
        older = _older_scheme_digest(poc)
        assert older != now
        session = session_service.get_session(db_session, uuid.UUID(sid))
        content = dict(session.session_metadata[session_service.APPROVED_CONTENT_KEY])
        content["package"] = older
        content.pop("package_scheme")
        session_service.update_session(
            db_session,
            session,
            SessionUpdate(
                metadata={
                    session_service.APPROVED_CONTENT_KEY: content,
                    session_service.RUN_PACKAGE_KEY: older,
                    session_service.SUCCESSFUL_RUN_PACKAGE_KEY: older,
                }
            ),
        )
    return created


def _detail(client, sid: str) -> dict:
    return client.get(f"/sessions/{sid}").json()


@requires_postgres
def test_a_session_approved_under_the_older_scheme_keeps_its_approval_and_its_download(
    client, db_session
) -> None:
    sid = _approved_session(client, db_session, "older", older_scheme=True)["id"]

    # The download, before anything has compared or re-based the approval.
    assert client.get(f"/sessions/{sid}/poc/deployable").status_code == 200
    # What a chat turn ends with.
    session = session_service.get_session(db_session, uuid.UUID(sid))
    assert sessions_router._reopen_if_approved_content_changed(db_session, session) is False

    detail = _detail(client, sid)
    assert detail["gate_statuses"]["gate_3"] == "approved"
    assert "gate_reopened" not in detail["metadata"]
    assert detail["metadata"]["last_successful_run"] == "run-1"
    assert client.get(f"/sessions/{sid}/poc/deployable").status_code == 200


def _as_scheme_2(db_session, sid: str, poc: str) -> None:
    """Store what a session approved and tested under scheme 2 holds."""
    session = session_service.get_session(db_session, uuid.UUID(sid))
    content = dict(session.session_metadata[session_service.APPROVED_CONTENT_KEY])
    content["package"] = _scheme_2_digest(poc)
    content["package_scheme"] = 2
    session_service.update_session(
        db_session,
        session,
        SessionUpdate(
            metadata={
                session_service.APPROVED_CONTENT_KEY: content,
                session_service.RUN_PACKAGE_KEY: content["package"],
                session_service.SUCCESSFUL_RUN_PACKAGE_KEY: content["package"],
            }
        ),
    )


@requires_postgres
def test_a_session_approved_under_scheme_2_keeps_its_approval_until_a_data_file_changes(
    client, db_session
) -> None:
    created = _approved_session(client, db_session, "scheme-2", older_scheme=False)
    sid = created["id"]
    poc = os.path.join(created["output_dir"], "poc")
    _as_scheme_2(db_session, sid, poc)
    assert _scheme_2_digest(poc) != sessions_router._approved_package_digest(poc)

    # Nothing changed: the approval and the download stand.
    assert client.get(f"/sessions/{sid}/poc/deployable").status_code == 200
    session = session_service.get_session(db_session, uuid.UUID(sid))
    assert sessions_router._reopen_if_approved_content_changed(db_session, session) is False
    assert _detail(client, sid)["gate_statuses"]["gate_3"] == "approved"

    # An edit the older scheme did not see is seen now.
    saved = _save(client, sid, "labels.json", '["invoice"]\n')

    assert saved.json()["gate_reopened"] == "gate_3"
    assert client.get(f"/sessions/{sid}/poc/deployable").status_code == 409


@requires_postgres
def test_an_edit_outside_the_digest_leaves_such_a_session_approved_and_open(
    client, db_session
) -> None:
    sid = _approved_session(client, db_session, "older-readme", older_scheme=True)["id"]

    saved = _save(client, sid, "README.md", "# Edited\n")

    assert saved.status_code == 200 and saved.json()["gate_reopened"] is None
    detail = _detail(client, sid)
    assert detail["gate_statuses"]["gate_3"] == "approved"
    approved = detail["metadata"][session_service.APPROVED_CONTENT_KEY]
    assert approved["package_scheme"] == sessions_router._PACKAGE_DIGEST_SCHEME
    assert client.get(f"/sessions/{sid}/poc/deployable").status_code == 200


@requires_postgres
@pytest.mark.parametrize("path", ["pdf_report.py", "run_poc.py"])
def test_an_edit_to_a_module_reopens_gate_3_in_such_a_session_too(client, db_session, path) -> None:
    """The approval is re-based on the package before the save, not after it: after it,
    the edit would be part of what the approval was re-based on, and go unseen."""
    sid = _approved_session(client, db_session, f"older-{path}", older_scheme=True)["id"]
    assert _file(client, sid, path).json()["affects_package"] is True

    saved = _save(client, sid, path, "print('edited after approval')\n")

    assert saved.status_code == 200
    assert saved.json()["gate_reopened"] == "gate_3"
    detail = _detail(client, sid)
    assert detail["gate_statuses"]["gate_3"] == "pending"
    assert detail["metadata"]["last_successful_run"] is None
    assert client.get(f"/sessions/{sid}/poc/deployable").status_code == 409


@requires_postgres
@pytest.mark.parametrize("path", ["helpers/dates.py", "input_bundle.py", "evals/run_evals.py"])
def test_an_edit_to_any_python_file_reopens_gate_3(client, db_session, path) -> None:
    sid = _approved_session(client, db_session, f"now-{path}", older_scheme=False)["id"]

    saved = _save(client, sid, path, "print('edited')\n")

    assert saved.json()["gate_reopened"] == "gate_3"
    assert _detail(client, sid)["gate_statuses"]["gate_3"] == "pending"


@requires_postgres
@pytest.mark.parametrize(
    ("path", "content"),
    [
        ("labels.json", '["invoice", "receipt", "credit note"]\n'),
        (".env.example", "AZURE_API_KEY=\nTAVILY_API_KEY=\n"),
        ("templates/report.md", "# The report, edited\n"),
    ],
)
def test_an_edit_to_a_file_that_is_not_code_reopens_gate_3_too(
    client, db_session, path, content
) -> None:
    """A data file run_poc.py reads (a root ``labels.json``) changes what the run does as
    much as the code: its edit must not leave the approval and the download standing."""
    sid = _approved_session(client, db_session, f"now-{path}", older_scheme=False)["id"]
    assert _file(client, sid, path).json()["affects_package"] is True

    saved = _save(client, sid, path, content)

    assert saved.status_code == 200, saved.text
    assert saved.json()["affects_package"] is True
    assert saved.json()["gate_reopened"] == "gate_3"
    detail = _detail(client, sid)
    assert detail["gate_statuses"]["gate_3"] == "pending"
    assert detail["metadata"]["last_successful_run"] is None
    assert client.get(f"/sessions/{sid}/poc/deployable").status_code == 409


@requires_postgres
def test_only_a_readme_keeps_the_approval(client, db_session) -> None:
    sid = _approved_session(client, db_session, "now-readme", older_scheme=False)["id"]
    assert _file(client, sid, "README.md").json()["affects_package"] is False

    saved = _save(client, sid, "README.md", "# Edited\n")

    assert saved.status_code == 200 and saved.json()["gate_reopened"] is None
    assert _detail(client, sid)["gate_statuses"]["gate_3"] == "approved"
    assert client.get(f"/sessions/{sid}/poc/deployable").status_code == 200


def _tested_session(client, db_session, user: str, digest_of) -> dict:
    """A package with a passed run recorded on it; Gate 3 not approved yet."""
    created = client.post("/sessions", json={"user_id": user, "title": "Digest"}).json()
    write_gate_artifacts(created["output_dir"], "gate_3")
    poc = os.path.join(created["output_dir"], "poc")
    _package(poc)
    session = session_service.get_session(db_session, uuid.UUID(created["id"]))
    session_service.update_session(
        db_session,
        session,
        SessionUpdate(
            metadata={
                "last_successful_run": "run-1",
                session_service.SUCCESSFUL_RUN_PACKAGE_KEY: digest_of(poc),
            }
        ),
    )
    return created


@requires_postgres
def test_before_gate_3_an_edit_to_another_module_closes_the_download(client, db_session) -> None:
    sid = _tested_session(client, db_session, "tested", sessions_router._approved_package_digest)[
        "id"
    ]
    assert client.get(f"/sessions/{sid}/poc/deployable").status_code == 200

    _save(client, sid, "input_bundle.py", "def bundle():\n    return ['edited']\n")

    refused = client.get(f"/sessions/{sid}/poc/deployable")
    assert refused.status_code == 409
    assert refused.json()["detail"]["error"] == "package_changed_since_run"


@requires_postgres
def test_before_gate_3_an_edit_to_a_data_file_closes_the_download(client, db_session) -> None:
    sid = _tested_session(
        client, db_session, "tested-data", sessions_router._approved_package_digest
    )["id"]
    assert client.get(f"/sessions/{sid}/poc/deployable").status_code == 200

    _save(client, sid, "labels.json", '["invoice"]\n')

    refused = client.get(f"/sessions/{sid}/poc/deployable")
    assert refused.status_code == 409
    assert refused.json()["detail"]["error"] == "package_changed_since_run"
    session = session_service.get_session(db_session, uuid.UUID(sid))
    # Gate 3 asks for the same new run.
    assert sessions_router._successful_run_is_of_another_package(session) is True


@requires_postgres
def test_before_gate_3_a_run_of_the_older_scheme_asks_for_a_new_run_as_the_gate_does(
    client, db_session
) -> None:
    """The scheme is kept with the approval, not with the run. A run recorded under the
    older one cannot be compared with today's digest: Gate 3 is refused on it until a
    new run has passed, and the download waits for the same run."""
    sid = _tested_session(client, db_session, "tested-older", _older_scheme_digest)["id"]

    refused = client.get(f"/sessions/{sid}/poc/deployable")

    assert refused.status_code == 409
    assert refused.json()["detail"]["error"] == "package_changed_since_run"
    session = session_service.get_session(db_session, uuid.UUID(sid))
    assert sessions_router._successful_run_is_of_another_package(session) is True


# --- a comparison that fails must not leave an untested edit approved -------------


def _fail_after(monkeypatch, calls_before_failing: int) -> None:
    """Let the approved-content comparison work ``calls_before_failing`` times, then raise."""
    real = sessions_router._reopen_if_approved_content_changed
    seen = {"calls": 0}

    def comparison(db, session):
        seen["calls"] += 1
        if seen["calls"] > calls_before_failing:
            raise RuntimeError("the comparison could not be made")
        return real(db, session)

    monkeypatch.setattr(sessions_router, "_reopen_if_approved_content_changed", comparison)


@requires_postgres
def test_an_edit_whose_comparison_fails_reopens_gate_3_anyway(
    client, db_session, monkeypatch
) -> None:
    sid = _approved_session(client, db_session, "fails-after", older_scheme=False)["id"]
    # The one before the save works; the one after it raises.
    _fail_after(monkeypatch, 1)

    saved = _save(client, sid, "pdf_report.py", "def render():\n    return 'untested'\n")

    assert saved.status_code == 200
    assert saved.json()["gate_reopened"] == "gate_3"
    detail = _detail(client, sid)
    assert detail["gate_statuses"]["gate_3"] == "pending"
    assert detail["metadata"]["last_successful_run"] is None
    assert client.get(f"/sessions/{sid}/poc/deployable").status_code == 409


@requires_postgres
def test_when_the_gate_cannot_be_reopened_either_the_download_still_refuses(
    client, db_session, monkeypatch
) -> None:
    sid = _approved_session(client, db_session, "fails-twice", older_scheme=False)["id"]
    assert client.get(f"/sessions/{sid}/poc/deployable").status_code == 200
    _fail_after(monkeypatch, 1)

    def no_reopening(*args, **kwargs):
        raise RuntimeError("the gate could not be reopened")

    monkeypatch.setattr(session_service, "reopen_gate", no_reopening)

    saved = _save(client, sid, "run_poc.py", "print('untested')\n")

    assert saved.status_code == 200 and saved.json()["gate_reopened"] is None
    # The approval is still on record, and the package it names is not this one.
    assert _detail(client, sid)["gate_statuses"]["gate_3"] == "approved"
    refused = client.get(f"/sessions/{sid}/poc/deployable")
    assert refused.status_code == 409
    assert refused.json()["detail"]["error"] == "package_changed_since_run"


@requires_postgres
def test_a_failed_comparison_takes_nothing_back_for_a_file_outside_the_digest(
    client, db_session, monkeypatch
) -> None:
    sid = _approved_session(client, db_session, "fails-readme", older_scheme=False)["id"]
    _fail_after(monkeypatch, 0)

    saved = _save(client, sid, "README.md", "# Edited\n")

    assert saved.status_code == 200 and saved.json()["gate_reopened"] is None
    assert _detail(client, sid)["gate_statuses"]["gate_3"] == "approved"
    assert client.get(f"/sessions/{sid}/poc/deployable").status_code == 200
