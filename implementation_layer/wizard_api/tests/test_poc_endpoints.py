"""PoC package endpoints (#151): listing and zip download."""

import importlib.util
import io
import os
import uuid
import zipfile

from helpers import requires_postgres, write_gate_artifacts
from wizard_api.models import WizardSession
from wizard_api.services import session_service


def _session_output_dir(db_session, session_id: str) -> str:
    session = session_service.get_session(db_session, uuid.UUID(session_id))
    return session.output_dir


def _session_ready_to_generate(client, title: str = "PoC") -> dict:
    """A session whose Gate 2 is approved.

    Generating scaffolds from the *approved* blueprint, so the endpoint now
    requires that approval (R6). These tests are about what generation produces,
    not about the gate, so they start past it.
    """
    created = client.post("/sessions", json={"user_id": "poc-user", "title": title}).json()
    write_gate_artifacts(created["output_dir"], "gate_2")
    client.patch(
        f"/sessions/{created['id']}",
        json={"gate_statuses": {"gate_2": "approved"}},
    )
    # The files only stood in for the agent's to get past the gate; each test
    # writes the design it is about.
    for name in ("use_case.blueprint.json", "workflow.bpmn"):
        os.remove(os.path.join(created["output_dir"], name))
    return created


_DESIGN = {
    "name": "Incident report extraction",
    "description": "Turn maintenance notes into structured incident reports.",
    "goal": "Show that a report can be produced from one note.",
    "steps": [
        {"id": "collect", "name": "Collect note", "type": "io"},
        {"id": "extract", "name": "Extract fields", "type": "ai", "component": "LLM"},
        {"id": "review", "name": "Technician review", "type": "human_review"},
        {"id": "deliver", "name": "Deliver report", "type": "io"},
    ],
}


def _session_with_a_design(client, title: str = "PoC") -> dict:
    """A session past Gate 2 whose blueprint is a small real design, not the seed.

    Generating from the seed is refused (#181), so the tests that are about what
    generation produces start from a design the wizard could have written.
    """
    created = _session_ready_to_generate(client, title)
    client.post(f"/sessions/{created['id']}/versions", json={"note": "design", "content": _DESIGN})
    return created


def _write_poc(output_dir: str) -> None:
    """Stand in for the V1 Phase 10 scaffolder — a *complete* package.

    The entrypoint is ``run_poc.py``, which is what the scaffolder writes and
    what the sandbox Job runs, and it imports a component: a package that wires
    nothing is not offered as a download any more.
    """
    poc = os.path.join(output_dir, "poc")
    os.makedirs(os.path.join(poc, "schemas"), exist_ok=True)
    with open(os.path.join(poc, "run_poc.py"), "w", encoding="utf-8") as fh:
        fh.write("from gaik.software_components.extractor import Extractor\n")
    with open(os.path.join(poc, "requirements.txt"), "w", encoding="utf-8") as fh:
        fh.write("gaik[extract]\n")
    with open(os.path.join(poc, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("# PoC\n")
    with open(os.path.join(poc, "schemas", "output_schema.json"), "w", encoding="utf-8") as fh:
        fh.write("{}\n")


def _write_partial_poc(output_dir: str) -> None:
    """What the report actually found behind the download button: a few schema
    files, no entrypoint, no requirements, no README."""
    poc = os.path.join(output_dir, "poc")
    os.makedirs(os.path.join(poc, "schemas"), exist_ok=True)
    with open(os.path.join(poc, "schemas", "output_schema.json"), "w", encoding="utf-8") as fh:
        fh.write("{}\n")


@requires_postgres
def test_poc_files_reports_nothing_until_the_scaffolder_has_run(client, db_session) -> None:
    created = client.post("/sessions", json={"user_id": "poc-user", "title": "PoC"}).json()

    listed = client.get(f"/sessions/{created['id']}/poc/files")
    assert listed.status_code == 200
    assert listed.json() == {"generated": False, "files": []}

    # And the download says 404 rather than handing back an empty archive.
    assert client.get(f"/sessions/{created['id']}/poc").status_code == 404


@requires_postgres
def test_poc_files_and_zip_expose_the_generated_package(client, db_session) -> None:
    created = client.post("/sessions", json={"user_id": "poc-user", "title": "PoC"}).json()
    session_id = created["id"]
    _write_poc(_session_output_dir(db_session, session_id))

    listed = client.get(f"/sessions/{session_id}/poc/files").json()
    assert listed["generated"] is True
    assert listed["ready"] is True
    assert listed["problems"] == []
    assert listed["files"] == [
        "README.md",
        "requirements.txt",
        "run_poc.py",
        "schemas/output_schema.json",
    ]

    got = client.get(f"/sessions/{session_id}/poc")
    assert got.status_code == 200
    assert got.headers["content-type"] == "application/zip"
    assert f"poc-{session_id}.zip" in got.headers["content-disposition"]

    # Entries keep the poc/ prefix so the archive unpacks into its own folder.
    with zipfile.ZipFile(io.BytesIO(got.content)) as zf:
        assert sorted(zf.namelist()) == [
            "poc/AI-GENERATED.json",
            "poc/README.md",
            "poc/requirements.txt",
            "poc/run_poc.py",
            "poc/schemas/output_schema.json",
        ]
        assert b"gaik" in zf.read("poc/run_poc.py")


@requires_postgres
def test_poc_endpoints_404_for_an_unknown_session(client) -> None:
    missing = uuid.uuid4()
    assert client.get(f"/sessions/{missing}/poc/files").status_code == 404
    assert client.get(f"/sessions/{missing}/poc").status_code == 404


# ---------------------------------------------------------------------------
# #93 — generating the package from the session's blueprint
# ---------------------------------------------------------------------------

import json  # noqa: E402

import pytest  # noqa: E402
from wizard_api.services import artifact_sync, poc_service  # noqa: E402

requires_scaffolder = pytest.mark.skipif(
    not poc_service.solution_wizard_available(),
    reason="solution_wizard is not installed",
)

#: The output the user agreed at the Specification step. The agent writes it to
#: the draft blueprint; the V2 blueprint in the database does not carry it.
_AGREED_SPEC = {
    "schema_name": "IncidentReport",
    "fields": ["incident_id", "severity", "summary"],
    "field_types": {"incident_id": "str", "severity": "str", "summary": "str"},
    "required_fields": ["incident_id", "severity"],
    "optional_fields": ["summary"],
    "allowed_values": {"severity": ["low", "high"]},
}


def _write_draft(output_dir: str, spec: dict) -> None:
    path = artifact_sync.artifact_path(output_dir, artifact_sync.DRAFT_BLUEPRINT_FILE)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"target_output_spec": spec}, fh)


def _write_v1_draft(output_dir: str, blueprint: dict) -> None:
    """Write the agent's own complete V1 blueprint to use_case.blueprint.json —
    the artifact it produces at spec generation, the source #167 makes the
    scaffolder prefer over the minimal v2_to_v1_dict conversion."""
    path = artifact_sync.artifact_path(output_dir, artifact_sync.DRAFT_BLUEPRINT_FILE)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(blueprint, fh)


@requires_scaffolder
@pytest.mark.parametrize(
    "module_id, input_types, expected_pattern",
    [
        ("audio_to_structured_data", ["audio"], "audio_to_structured"),
        ("documents_to_structured_data", ["pdf"], "document_to_structured"),
        ("rag_workflow", ["document_collection"], "rag"),
    ],
)
def test_generate_scaffolds_the_agents_draft_pattern_not_generic(
    tmp_path, module_id, input_types, expected_pattern
) -> None:
    """#167: the agent's draft carries the selected module, so scaffolding from
    it wires the case's own pattern. ``v2_to_v1_dict`` is minimal — it drops the
    module into ``selected_building_blocks`` and hard-codes ``input_types`` — so
    the pattern never matches and the scaffolder falls back to ``_generic``: a
    ``run_poc.py`` that imports nothing and does nothing. The fix prefers the
    draft, so "Aja PoC" for audio/document/RAG produces the wired pattern.
    """
    output_dir = str(tmp_path)
    _write_v1_draft(
        output_dir,
        {
            "use_case": {
                "id": "uc",
                "name": "Draft-driven PoC",
                "description": "The agent selected a single covering module.",
                "domain": "manufacturing",
            },
            "technical_spec": {"input_types": input_types},
            "target_output_spec": _AGREED_SPEC,
            "components": {
                "selected_modules": [{"id": module_id, "name": module_id}],
                "selected_building_blocks": [],
            },
        },
    )

    # The V2 blueprint is deliberately the minimal shape v2_to_v1_dict would turn
    # into _generic; the fix must scaffold from the valid draft instead of it.
    result = poc_service.generate_poc(
        {"use_case": {"title": "Draft-driven PoC"}},
        session_id="draft-session",
        output_dir=output_dir,
    )

    assert result["source"] == "scaffolder"
    assert result["pattern"] == expected_pattern
    assert result["template_wired"] is True

    run_poc = open(os.path.join(output_dir, "poc", "run_poc.py"), encoding="utf-8").read()
    assert "your pipeline" not in run_poc.lower()  # not the _generic TODO skeleton


@requires_scaffolder
def test_generate_falls_back_to_conversion_without_a_valid_draft(tmp_path) -> None:
    """No agent draft (or an unparseable one) → the V2 → V1 conversion still runs,
    so "Aja PoC" never fails for want of a draft. The bare spec below is not a
    valid V1 Blueprint, standing in for a half-written file."""
    output_dir = str(tmp_path)
    _write_v1_draft(output_dir, {"target_output_spec": _AGREED_SPEC})

    result = poc_service.generate_poc(
        {"use_case": {"title": "No module selected"}},
        session_id="fallback-session",
        output_dir=output_dir,
        target_output_spec=_AGREED_SPEC,
    )

    assert result["source"] == "scaffolder"
    assert result["pattern"] == "_generic"
    schema = open(
        os.path.join(output_dir, "poc", "schemas", "output_schema.py"), encoding="utf-8"
    ).read()
    assert "class IncidentReport(BaseModel):" in schema  # override still applied


@requires_postgres
@requires_scaffolder
def test_generate_produces_the_v1_scaffolder_file_set(client, db_session) -> None:
    created = _session_with_a_design(client)
    session_id = created["id"]

    generated = client.post(f"/sessions/{session_id}/poc/generate")
    assert generated.status_code == 200
    body = generated.json()
    assert body["generated"] is True
    assert body["regenerated"] is False

    # The same set scaffold_poc writes — the endpoint adds nothing of its own
    # beyond the manifest, which is hidden from the listing. The model file is
    # written exactly where gaik can describe the schema (gaik installed).
    model_file = "schemas/output_schema_model.json"
    assert (model_file in body["files"]) == (importlib.util.find_spec("gaik") is not None)
    assert set(body["files"]) - {model_file} == {
        ".env.example",
        "README.md",
        "app.py",
        "config.yaml",
        # New with the upstream sync: the scaffolder now writes a provider
        # config beside the rest.
        "provider_config.py",
        # The manifest lookup every package gets (#251).
        "document_manifest.py",
        # And the input finder (#255).
        "input_bundle.py",
        # Counts unless --verbose, one-line errors unless --debug (upstream's
        # governance and PoC output change, brought in with the upstream main sync).
        "poc_output.py",
        "evals/ground_truth/.gitkeep",
        "evals/run_basic_eval.py",
        "prompts/extraction_requirements.md",
        "requirements.txt",
        "run_poc.py",
        "schemas/output_schema.json",
        "schemas/output_schema.py",
        "schemas/output_schema_requirements.json",
        # The package's test page: its server, the page and the blueprint's facts as data,
        # and the page's own files (its font with the licence, the GAIK mark).
        "ui/index.html",
        "ui/solution.json",
        "ui/fonts/sora-latin-wght-normal.woff2",
        "ui/fonts/sora-latin-ext-wght-normal.woff2",
        "ui/fonts/OFL.txt",
        "ui/gaik.svg",
    }

    # And the package is immediately visible to the endpoints that serve it.
    listed = client.get(f"/sessions/{session_id}/poc/files").json()
    assert listed["generated"] is True
    assert "run_poc.py" in listed["files"]
    assert poc_service.MANIFEST_NAME not in listed["files"]
    # This blueprint scaffolds the hybrid skeleton, whose unwired step is a
    # `None  # TODO: wire ...` line: listed, but not offered until the agent
    # has filled it in (#252).
    assert listed["ready"] is False
    assert any("TODO marker" in problem for problem in listed["problems"])
    assert client.get(f"/sessions/{session_id}/poc").status_code == 409


@requires_postgres
@requires_scaffolder
def test_generated_schema_uses_the_agreed_output_fields(client, db_session) -> None:
    created = _session_ready_to_generate(client, "Incidents")
    session_id = created["id"]
    output_dir = _session_output_dir(db_session, session_id)
    _write_draft(output_dir, _AGREED_SPEC)

    client.post(f"/sessions/{session_id}/poc/generate")

    schema = open(
        os.path.join(output_dir, "poc", "schemas", "output_schema.py"), encoding="utf-8"
    ).read()
    # Without the override the V2 → V1 adapter hands the scaffolder a
    # placeholder ("Output" with a single "result" field), so every PoC would
    # ship a dummy schema instead of the one the user agreed to.
    assert "class IncidentReport(BaseModel):" in schema
    assert "incident_id" in schema and "severity" in schema
    assert "class Output(BaseModel):" not in schema


@requires_postgres
@requires_scaffolder
def test_regenerating_after_a_blueprint_change_is_not_a_silent_no_op(client, db_session) -> None:
    created = _session_ready_to_generate(client, "Incidents")
    session_id = created["id"]
    output_dir = _session_output_dir(db_session, session_id)
    _write_draft(output_dir, _AGREED_SPEC)

    client.post(f"/sessions/{session_id}/poc/generate")
    schema_path = os.path.join(output_dir, "poc", "schemas", "output_schema.py")
    before = open(schema_path, encoding="utf-8").read()
    assert "class IncidentReport(BaseModel):" in before

    # The user reworks the agreed output and the PoC is generated again.
    _write_draft(
        output_dir,
        {
            "schema_name": "ServiceRequest",
            "fields": ["request_id", "channel"],
            "field_types": {"request_id": "str", "channel": "str"},
            "required_fields": ["request_id", "channel"],
        },
    )
    again = client.post(f"/sessions/{session_id}/poc/generate")
    assert again.status_code == 200
    assert again.json()["regenerated"] is True
    assert again.json()["blueprint_changed"] is True

    after = open(schema_path, encoding="utf-8").read()
    # scaffold_poc leaves an existing output_schema.py alone so a schema the
    # user reviewed mid-conversation survives. That guard would freeze our own
    # output too, which is exactly the no-op this test forbids.
    assert "class ServiceRequest(BaseModel):" in after
    assert "class IncidentReport(BaseModel):" not in after


@requires_postgres
@requires_scaffolder
def test_regenerating_keeps_sample_inputs_and_earlier_results(client, db_session) -> None:
    created = _session_with_a_design(client)
    session_id = created["id"]
    output_dir = _session_output_dir(db_session, session_id)

    client.post(f"/sessions/{session_id}/poc/generate")
    poc = os.path.join(output_dir, "poc")
    with open(os.path.join(poc, "sample_input", "case.txt"), "w", encoding="utf-8") as fh:
        fh.write("a real input the user dropped in\n")
    with open(os.path.join(poc, "output", "result.json"), "w", encoding="utf-8") as fh:
        fh.write('{"from": "an earlier run"}\n')

    client.post(f"/sessions/{session_id}/poc/generate")

    assert open(os.path.join(poc, "sample_input", "case.txt"), encoding="utf-8").read()
    assert open(os.path.join(poc, "output", "result.json"), encoding="utf-8").read()


@requires_postgres
def test_generate_404s_for_an_unknown_session(client) -> None:
    assert client.post(f"/sessions/{uuid.uuid4()}/poc/generate").status_code == 404


@requires_postgres
@requires_scaffolder
def test_generate_never_overwrites_the_agents_own_package(client, db_session) -> None:
    """The agent wires the real GAIK component for the case's own pattern and can
    add synthetic test data and an eval rubric. Scaffolding over that would trade
    a working, case-specific PoC for a generic template (found while reviewing a
    live use-case run: every generated PoC was pattern-specific, none generic)."""
    created = _session_with_a_design(client, "UC04")
    session_id = created["id"]
    output_dir = _session_output_dir(db_session, session_id)

    agent_run = (
        '"""UC04 extraction PoC — written by the agent."""\n'
        "from gaik.software_components.extractor import DataExtractor\n"
        "extractor = DataExtractor(schema=IncidentReport)\n"
    )
    poc = os.path.join(output_dir, "poc")
    os.makedirs(poc, exist_ok=True)
    with open(os.path.join(poc, "run_poc.py"), "w", encoding="utf-8") as fh:
        fh.write(agent_run)

    body = client.post(f"/sessions/{session_id}/poc/generate").json()
    assert body["source"] == "agent"
    assert body["scaffolded"] is False
    assert body["files"] == ["run_poc.py"]

    # Untouched: still the agent's wiring, not the generic template.
    with open(os.path.join(poc, "run_poc.py"), encoding="utf-8") as fh:
        assert fh.read() == agent_run

    # force=true is the deliberate escape hatch when the blueprint has moved on.
    forced = client.post(f"/sessions/{session_id}/poc/generate?force=true").json()
    assert forced["source"] == "scaffolder"
    assert forced["scaffolded"] is True
    with open(os.path.join(poc, "run_poc.py"), encoding="utf-8") as fh:
        assert "written by the agent" not in fh.read()


@requires_postgres
@requires_scaffolder
def test_schema_and_prompt_alone_are_built_on_not_kept_as_a_package(client, db_session) -> None:
    """The agent writes schemas/ and prompts/ at the schema-design step, long
    before a package exists. Treating those as "the agent's package" shipped a
    download with no run_poc.py (found in a live UC01 run). They are the
    approved schema and prompt: the scaffolder builds the package around them,
    keeps them as written, and a regeneration must not delete them."""
    created = _session_ready_to_generate(client, "UC01")
    session_id = created["id"]
    output_dir = _session_output_dir(db_session, session_id)
    _write_draft(output_dir, _AGREED_SPEC)

    poc = os.path.join(output_dir, "poc")
    approved_schema = (
        "from pydantic import BaseModel\n\n"
        "class IncidentReport(BaseModel):\n"
        "    incident_id: str  # approved in the conversation\n"
    )
    approved_prompt = "# Extraction requirements — approved in the conversation\n"
    os.makedirs(os.path.join(poc, "schemas", "__pycache__"), exist_ok=True)
    os.makedirs(os.path.join(poc, "prompts"), exist_ok=True)
    with open(os.path.join(poc, "schemas", "output_schema.py"), "w", encoding="utf-8") as fh:
        fh.write(approved_schema)
    with open(
        os.path.join(poc, "schemas", "output_schema_requirements.json"), "w", encoding="utf-8"
    ) as fh:
        json.dump({"schema_name": "IncidentReport"}, fh)
    with open(
        os.path.join(poc, "prompts", "extraction_requirements.md"), "w", encoding="utf-8"
    ) as fh:
        fh.write(approved_prompt)
    with open(
        os.path.join(poc, "schemas", "__pycache__", "output_schema.cpython-311.pyc"), "wb"
    ) as fh:
        fh.write(b"\x00")

    body = client.post(f"/sessions/{session_id}/poc/generate").json()
    assert body["source"] == "scaffolder"
    assert body["scaffolded"] is True
    assert {"run_poc.py", "requirements.txt", "README.md"} <= set(body["files"])
    assert not any("__pycache__" in f for f in body["files"])

    def read(*parts: str) -> str:
        with open(os.path.join(poc, *parts), encoding="utf-8") as fh:
            return fh.read()

    assert read("schemas", "output_schema.py") == approved_schema
    assert read("prompts", "extraction_requirements.md") == approved_prompt

    again = client.post(f"/sessions/{session_id}/poc/generate").json()
    assert again["regenerated"] is True
    assert read("schemas", "output_schema.py") == approved_schema
    assert read("prompts", "extraction_requirements.md") == approved_prompt
    assert "run_poc.py" in again["files"]


@requires_postgres
@requires_scaffolder
def test_regenerating_never_overwrites_the_agents_wiring(client, db_session) -> None:
    """A composed pipeline has no template, so the scaffolder writes a TODO
    stub and the agent wires it in the conversation. Pressing "Aja PoC" again
    used to clear "our" run_poc.py and put the stub back over that work (found
    in a live UC02 run with VisionExtractor)."""
    created = _session_ready_to_generate(client, "UC02")
    session_id = created["id"]
    output_dir = _session_output_dir(db_session, session_id)
    _write_draft(output_dir, _AGREED_SPEC)

    first = client.post(f"/sessions/{session_id}/poc/generate").json()
    assert first["source"] == "scaffolder"

    run_poc = os.path.join(output_dir, "poc", "run_poc.py")
    wired = (
        '"""Wired by the agent."""\n'
        "from gaik.software_components.vision_extractor import VisionExtractor\n"
    )
    with open(run_poc, "w", encoding="utf-8") as fh:
        fh.write(wired)

    again = client.post(f"/sessions/{session_id}/poc/generate").json()
    assert again["source"] == "agent"
    assert again["scaffolded"] is False
    with open(run_poc, encoding="utf-8") as fh:
        assert fh.read() == wired

    forced = client.post(f"/sessions/{session_id}/poc/generate?force=true").json()
    assert forced["source"] == "scaffolder"
    with open(run_poc, encoding="utf-8") as fh:
        assert "Wired by the agent" not in fh.read()


@requires_postgres
def test_an_incomplete_package_is_not_offered_as_a_download(client, db_session) -> None:
    """19 / T8: the download was live as soon as any file existed under poc/."""
    created = client.post("/sessions", json={"user_id": "poc-user"}).json()
    _write_partial_poc(_session_output_dir(db_session, created["id"]))

    listed = client.get(f"/sessions/{created['id']}/poc/files").json()
    assert listed["generated"] is True
    assert listed["ready"] is False
    assert "run_poc.py is missing" in listed["problems"]

    refused = client.get(f"/sessions/{created['id']}/poc")
    assert refused.status_code == 409
    assert refused.json()["detail"]["error"] == "poc_package_incomplete"


@requires_postgres
def test_the_package_cannot_be_generated_before_gate_2_is_approved(client) -> None:
    """R6: the button worked at Gate 2 and reported success over a blueprint
    nobody had approved. A fresh session on purpose — no gate approved."""
    created = client.post("/sessions", json={"user_id": "poc-gate"}).json()

    refused = client.post(f"/sessions/{created['id']}/poc/generate")

    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["error"] == "gate_not_approved"
    assert detail["gate"] == "gate_2"


# ---------------------------------------------------------------------------
# Sandbox runs (#91 / #92)
# ---------------------------------------------------------------------------


@requires_postgres
def test_a_run_cannot_start_before_gate_2_is_approved(client) -> None:
    created = client.post("/sessions", json={"user_id": "run-user"}).json()

    refused = client.post(f"/sessions/{created['id']}/runs")

    assert refused.status_code == 409
    assert refused.json()["detail"]["error"] == "gate_not_approved"


@requires_postgres
def test_a_run_cannot_start_without_a_package(client) -> None:
    created = _session_ready_to_generate(client, "run-no-package")

    refused = client.post(f"/sessions/{created['id']}/runs")

    assert refused.status_code == 409
    assert "no PoC package" in refused.json()["detail"]["message"]


@requires_postgres
def test_a_run_cannot_start_on_an_incomplete_package(client, db_session) -> None:
    """A ten-minute Job to prove an unwired package does nothing helps nobody."""
    created = _session_ready_to_generate(client, "run-partial")
    _write_partial_poc(_session_output_dir(db_session, created["id"]))

    refused = client.post(f"/sessions/{created['id']}/runs")

    assert refused.status_code == 409
    assert refused.json()["detail"]["error"] == "poc_package_incomplete"


@requires_postgres
def test_a_run_says_what_the_deployment_is_missing(client, db_session) -> None:
    """With a complete package the request is legitimate, so a failure here is
    the deployment's: a 503 with a code, not a 500. Which piece is missing is
    for the log; the answer names no setting or path."""
    created = _session_ready_to_generate(client, "run-ready")
    _write_poc(_session_output_dir(db_session, created["id"]))

    started = client.post(f"/sessions/{created['id']}/runs")

    assert started.status_code in (201, 503)
    if started.status_code == 503:
        detail = started.json()["detail"]
        assert detail["error"] == "sandbox_unavailable"
        assert detail["trace_id"]
        for internal in ("namespace", "WIZARD_", "kubernetes", "pip install", "deploy/"):
            assert internal not in detail["message"]


@requires_postgres
def test_a_started_run_is_remembered_for_the_agent(client, db_session, monkeypatch) -> None:
    """The next chat message tells the agent about it (run_context, #96)."""
    from wizard_api.services import sandbox_runner

    class _Starts:
        def __init__(self, *args, **kwargs):
            pass

        def create_run(self, session_id, user_id=None):
            return "run-42"

    monkeypatch.setattr(sandbox_runner, "SandboxRunner", _Starts)
    created = _session_ready_to_generate(client, "run-remembered")
    _write_poc(_session_output_dir(db_session, created["id"]))

    assert client.post(f"/sessions/{created['id']}/runs").status_code == 201
    assert client.get(f"/sessions/{created['id']}").json()["metadata"]["latest_run"] == "run-42"


@requires_postgres
def test_a_started_run_keeps_the_names_of_the_inputs_it_ran_on(
    client, db_session, monkeypatch
) -> None:
    """The PoC tab tells a result from other material than what is listed now,
    also after a reload, when only the session says what the run read."""
    from wizard_api.services import sandbox_runner

    class _Starts:
        def __init__(self, *args, **kwargs):
            pass

        def create_run(self, session_id, user_id=None):
            return "run-43"

    monkeypatch.setattr(sandbox_runner, "SandboxRunner", _Starts)
    created = _session_ready_to_generate(client, "run-inputs")
    sid = created["id"]
    _write_poc(_session_output_dir(db_session, sid))
    client.post(
        f"/sessions/{sid}/poc/input",
        files={"file": ("order.pdf", b"%PDF-1.7", "application/pdf")},
    )

    started = client.post(f"/sessions/{sid}/runs")
    assert started.status_code == 201
    # Said with the run too: the tab may not have read the list when it started it.
    assert started.json()["inputs"] == ["order.pdf"]
    metadata = client.get(f"/sessions/{sid}").json()["metadata"]
    assert metadata["latest_run_inputs"] == ["order.pdf"]

    # The record is the server's: a caller cannot write it.
    refused = client.patch(f"/sessions/{sid}", json={"metadata": {"latest_run_inputs": ["x.pdf"]}})
    assert refused.status_code >= 400
    assert refused.json()["detail"]["error"] == "server_owned_metadata"

    # A file added after the run is not among them.
    client.post(
        f"/sessions/{sid}/poc/input",
        files={"file": ("later.pdf", b"%PDF-1.7", "application/pdf")},
    )
    assert client.get(f"/sessions/{sid}").json()["metadata"]["latest_run_inputs"] == ["order.pdf"]


@requires_postgres
def test_a_run_the_sandbox_has_no_room_for_is_told_to_try_again(
    client, db_session, monkeypatch
) -> None:
    """Every run reserves CPU from the project quota the other apps deploy from."""
    from wizard_api.services import sandbox_runner

    class _Full:
        def __init__(self, *args, **kwargs):
            pass

        def create_run(self, session_id, user_id=None):
            raise sandbox_runner.RunLimitError("the sandbox is busy")

    monkeypatch.setattr(sandbox_runner, "SandboxRunner", _Full)
    created = _session_ready_to_generate(client, "run-busy")
    _write_poc(_session_output_dir(db_session, created["id"]))

    refused = client.post(f"/sessions/{created['id']}/runs")

    assert refused.status_code == 429
    assert refused.json()["detail"]["error"] == "sandbox_busy"
    assert refused.headers["retry-after"] == "30"
    assert "latest_run" not in client.get(f"/sessions/{created['id']}").json()["metadata"]


@requires_postgres
def test_an_input_file_is_uploaded_listed_and_removed(client, db_session) -> None:
    """#95: the run view can hand the package a file, and the Job reads it at
    /workspace/poc/sample_input because the zip already carries it."""
    created = _session_ready_to_generate(client, "input-user")
    _write_poc(_session_output_dir(db_session, created["id"]))
    sid = created["id"]

    up = client.post(
        f"/sessions/{sid}/poc/input",
        files={"file": ("purchase-order.pdf", b"%PDF-1.7 ...", "application/pdf")},
    )
    assert up.status_code == 201
    assert up.json()["path"] == "sample_input/purchase-order.pdf"

    listed = client.get(f"/sessions/{sid}/poc/input").json()["files"]
    assert [(f["name"], f["uploaded"]) for f in listed] == [("purchase-order.pdf", True)]

    assert client.delete(f"/sessions/{sid}/poc/input/purchase-order.pdf").status_code == 204
    assert client.get(f"/sessions/{sid}/poc/input").json()["files"] == []


@requires_postgres
def test_an_uploaded_input_travels_with_the_package(client, db_session) -> None:
    """The point of putting it inside poc/: no manifest change is needed."""
    created = _session_ready_to_generate(client, "input-zip")
    _write_poc(_session_output_dir(db_session, created["id"]))
    sid = created["id"]
    client.post(
        f"/sessions/{sid}/poc/input",
        files={"file": ("incident.wav", b"RIFF....WAVE", "audio/wav")},
    )

    got = client.get(f"/sessions/{sid}/poc")

    assert got.status_code == 200
    with zipfile.ZipFile(io.BytesIO(got.content)) as zf:
        assert "poc/sample_input/incident.wav" in zf.namelist()


@requires_postgres
def test_an_upload_cannot_become_the_entrypoint(client, db_session) -> None:
    """run_poc.py is what the sandbox Job executes."""
    created = _session_ready_to_generate(client, "input-evil")
    output_dir = _session_output_dir(db_session, created["id"])
    _write_poc(output_dir)

    refused = client.post(
        f"/sessions/{created['id']}/poc/input",
        files={"file": ("../run_poc.py", b"import os; os.system('id')", "text/x-python")},
    )

    assert refused.status_code == 422
    entrypoint = os.path.join(output_dir, "poc", "run_poc.py")
    assert "gaik" in open(entrypoint, encoding="utf-8").read()


# ---------------------------------------------------------------------------
# Gate 3 refinement (#96)
# ---------------------------------------------------------------------------


@requires_postgres
def test_feedback_after_a_run_is_recorded_with_its_classification(client) -> None:
    created = _session_ready_to_generate(client, "refine")
    sid = created["id"]

    given = client.post(
        f"/sessions/{sid}/runs/run-1/feedback",
        json={"feedback": "Invoice lines come out as one text field", "classification": "intent"},
    )

    assert given.status_code == 201
    body = given.json()
    assert body["requires_blueprint_change"] is True
    assert "blueprint" in body["rule"]

    listed = client.get(f"/sessions/{sid}/refinements").json()["refinements"]
    assert listed[-1]["classification"] == "intent"
    assert listed[-1]["run_id"] == "run-1"


@requires_postgres
def test_empty_feedback_is_refused(client) -> None:
    created = _session_ready_to_generate(client, "refine-empty")

    refused = client.post(
        f"/sessions/{created['id']}/runs/run-1/feedback",
        json={"feedback": "  ", "classification": "intent"},
    )

    assert refused.status_code == 422


@requires_postgres
@requires_scaffolder
def test_an_intent_change_blocks_regeneration_until_the_blueprint_moves(client) -> None:
    """The rule V1 states in prose, held by the server: regenerating now would
    produce a package that disagrees with the blueprint it came from."""
    created = _session_with_a_design(client, "refine-block")
    sid = created["id"]
    client.post(
        f"/sessions/{sid}/runs/run-1/feedback",
        json={"feedback": "The schema needs a line-items list", "classification": "intent"},
    )

    blocked = client.post(f"/sessions/{sid}/poc/generate")

    assert blocked.status_code == 409
    assert blocked.json()["detail"]["error"] == "blueprint_change_required"

    # Once the blueprint has taken the change, the way forward opens.
    client.post(f"/sessions/{sid}/versions", json={"note": "line items"})
    assert client.post(f"/sessions/{sid}/poc/generate").status_code == 200


@requires_postgres
@requires_scaffolder
def test_an_implementation_fix_does_not_block_regeneration(client) -> None:
    created = _session_with_a_design(client, "refine-impl")
    sid = created["id"]
    client.post(
        f"/sessions/{sid}/runs/run-1/feedback",
        json={"feedback": "The output path is wrong", "classification": "implementation"},
    )

    assert client.post(f"/sessions/{sid}/poc/generate").status_code == 200


@requires_postgres
def test_the_deployable_package_needs_a_successful_run_first(client, db_session) -> None:
    """#143: handing over a package nobody has seen work is what the sandbox
    step exists to prevent."""
    created = _session_ready_to_generate(client, "deployable-gate")
    _write_poc(_session_output_dir(db_session, created["id"]))

    refused = client.get(f"/sessions/{created['id']}/poc/deployable")

    assert refused.status_code == 409
    assert refused.json()["detail"]["error"] == "no_successful_run"


@requires_postgres
def test_the_deployable_package_leaves_the_test_data_behind(client, db_session) -> None:
    created = _session_ready_to_generate(client, "deployable-ok")
    sid = created["id"]
    output_dir = _session_output_dir(db_session, sid)
    _write_poc(output_dir)

    # A sample input the developer uploaded, and a previous run's output.
    client.post(
        f"/sessions/{sid}/poc/input",
        files={"file": ("order.pdf", b"%PDF-1.7", "application/pdf")},
    )
    os.makedirs(os.path.join(output_dir, "poc", "output"), exist_ok=True)
    with open(os.path.join(output_dir, "poc", "output", "result.json"), "w") as fh:
        fh.write("{}")

    # A run that succeeded, as the stream would have recorded it. Written the
    # way the server does, because a PATCH setting it is refused (K2/#143).
    row = db_session.get(WizardSession, uuid.UUID(sid))
    row.session_metadata = {**row.session_metadata, "last_successful_run": "run-1"}
    db_session.commit()

    got = client.get(f"/sessions/{sid}/poc/deployable")

    assert got.status_code == 200
    assert got.headers["X-Wizard-Run-Id"] == "run-1"
    with zipfile.ZipFile(io.BytesIO(got.content)) as zf:
        names = zf.namelist()
    assert "poc/run_poc.py" in names
    assert "poc/requirements.txt" in names
    assert "poc/README.md" in names
    assert not any("sample_input" in n for n in names)
    assert not any("output/" in n for n in names)

    # The PoC tab lists the package as the zip carries it: the same names,
    # the AI marker the download writes included, the test data left out.
    listed = client.get(f"/sessions/{sid}/poc/files").json()
    assert sorted(listed["package_files"]) == sorted(names)
    assert "poc/AI-GENERATED.json" in listed["package_files"]
    assert any("sample_input" in f for f in listed["files"])


def _write_solution(output_dir: str, *, ui_view: bool = True) -> None:
    """The files the wizard leaves beside poc/: blueprint, diagrams, documentation."""
    files = {
        "use_case.blueprint.json": '{"technical_spec": {"model_provider": "azure"}}',
        "workflow.bpmn": "<definitions agent='yes'/>",
        "workflow.mmd": "flowchart LR\n  a --> b\n",
        "docs/user_guide.md": "# User guide\n",
        "docs/technical_specification.md": "# Technical specification\n",
        # Not documents the wizard writes: none of these is handed over.
        "docs/.env": "OPENAI_API_KEY=not-for-the-package\n",
        "docs/__pycache__/notes.cpython-312.pyc": "compiled",
        "docs/invoice-1001.pdf": "%PDF-1.4 a test document",
        "docs/notes.md": "# The agent's own notes\n",
    }
    if ui_view:
        files["ui_view/workflow.bpmn"] = "<definitions workspace='yes'/>"
        files["ui_view/blueprint.json"] = "{}"
    for name, text in files.items():
        path = os.path.join(output_dir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)


def _run_recorded(db_session, sid: str) -> None:
    row = db_session.get(WizardSession, uuid.UUID(sid))
    row.session_metadata = {**row.session_metadata, "last_successful_run": "run-1"}
    db_session.commit()


def _deployable(client, sid: str) -> dict[str, bytes]:
    got = client.get(f"/sessions/{sid}/poc/deployable")
    assert got.status_code == 200
    with zipfile.ZipFile(io.BytesIO(got.content)) as zf:
        entries = zf.namelist()
        # No file twice: one entry per name.
        assert len(set(entries)) == len(entries)
        return {name: zf.read(name) for name in entries}


def _draw_without_solution_wizard(monkeypatch) -> list[dict]:
    """Stand in for the BPMN generator, which needs solution_wizard; returns
    the blueprints it was asked to draw."""
    from wizard_api.services import ai_marking, bpmn_service

    asked: list[dict] = []

    def draw(blueprint, **_kwargs):
        asked.append(blueprint)
        return ai_marking.mark_xml("<definitions drawn='yes'/>")

    monkeypatch.setattr(bpmn_service, "generate_bpmn_xml", draw)
    return asked


@requires_scaffolder
def test_the_package_keeps_the_documents_the_generator_writes() -> None:
    from solution_wizard.docs_generator import DOC_NAMES

    assert list(poc_service.SOLUTION_DOC_NAMES) == DOC_NAMES


@requires_postgres
def test_the_deployable_package_carries_the_blueprint_the_diagrams_and_the_documentation(
    client, db_session, monkeypatch
) -> None:
    """Someone who receives only poc/ cannot tell which model, components and
    review steps were decided: the solution's own files go with the package."""
    asked = _draw_without_solution_wizard(monkeypatch)
    created = _session_with_a_design(client, "deployable-solution")
    sid = created["id"]
    output_dir = _session_output_dir(db_session, sid)
    _write_poc(output_dir)
    _write_solution(output_dir)
    _run_recorded(db_session, sid)

    package = _deployable(client, sid)

    names = set(package)
    assert {
        "poc/run_poc.py",
        "AI-GENERATED.json",
        "use_case.blueprint.json",
        "workflow.bpmn",
        "workflow.mmd",
        "docs/user_guide.md",
        "docs/technical_specification.md",
    } <= names
    # The blueprint as the wizard wrote it, model choices included.
    blueprint = json.loads(package["use_case.blueprint.json"])
    assert blueprint["technical_spec"]["model_provider"] == "azure"
    # The diagram is drawn from the session's blueprint, not copied from the
    # workspace's last chat turn, and it says once that a model made it.
    diagram = package["workflow.bpmn"].decode()
    assert "drawn='yes'" in diagram
    assert "workspace='yes'" not in diagram and "agent='yes'" not in diagram
    assert [step["name"] for step in asked[0]["steps"]][2] == "Technician review"
    assert diagram.count("<!-- ai_generated: true;") == 1
    # What the server wrote for the agent's own reading is not part of the hand-over.
    assert not any(name.startswith("ui_view/") for name in names)
    # Only the documents the wizard writes leave docs/: no secret, cache or test document.
    assert sorted(n for n in names if n.startswith("docs/")) == [
        "docs/technical_specification.md",
        "docs/user_guide.md",
    ]

    # The marker at the root says what each file beside poc/ was made from.
    marker = json.loads(package["AI-GENERATED.json"])
    version = client.get(f"/sessions/{sid}").json()["active_version"]
    assert marker["ai_generated"] is True
    assert marker["content"] == "solution-files-deployable"
    assert marker["blueprint_version"] == version
    assert marker["files"]["workflow.bpmn"] == {
        "made_from": "blueprint",
        "blueprint_version": version,
    }
    for name in ("use_case.blueprint.json", "workflow.mmd", "docs/user_guide.md"):
        assert marker["files"][name] == {"made_from": "agent_draft"}
    beside_poc = {n for n in names if not n.startswith("poc/")} - {"AI-GENERATED.json"}
    assert set(marker["files"]) == beside_poc

    listed = client.get(f"/sessions/{sid}/poc/files").json()
    assert listed["solution_files"] == [
        "use_case.blueprint.json",
        "workflow.bpmn",
        "workflow.mmd",
        "docs/technical_specification.md",
        "docs/user_guide.md",
    ]
    assert set(listed["solution_files"]) == beside_poc
    assert not any(name.startswith(("docs/", "workflow")) for name in listed["files"])


@requires_postgres
@requires_scaffolder
def test_the_package_diagram_follows_a_blueprint_saved_after_the_last_chat_turn(
    client, db_session
) -> None:
    """A save in the Blueprint form or the diagram does not rewrite
    ui_view/workflow.bpmn; the package's diagram is the saved blueprint all the same."""
    from wizard_api.services import blueprint_service

    created = _session_with_a_design(client, "deployable-after-edit")
    sid = created["id"]
    output_dir = _session_output_dir(db_session, sid)
    _write_poc(output_dir)
    _write_solution(output_dir)
    _run_recorded(db_session, sid)
    # The agent's draft was adopted as the design version.
    row = db_session.get(WizardSession, uuid.UUID(sid))
    adopted = blueprint_service.get_active_version(db_session, row)
    row.session_metadata = {
        **row.session_metadata,
        artifact_sync.ADOPTED_DRAFT_KEY: artifact_sync.content_digest(adopted.content),
    }
    db_session.commit()

    edited = json.loads(json.dumps(_DESIGN))
    edited["steps"][2]["name"] = "Supervisor sign-off"
    saved = client.patch(f"/sessions/{sid}/blueprint", json={"content": edited})
    assert saved.status_code == 200
    version = saved.json()["active_version"]

    package = _deployable(client, sid)

    diagram = package["workflow.bpmn"].decode()
    assert "Supervisor sign-off" in diagram
    assert "Technician review" not in diagram
    marker = json.loads(package["AI-GENERATED.json"])
    assert marker["files"]["workflow.bpmn"]["blueprint_version"] == version
    assert diagram.count("<!-- ai_generated: true;") == 1
    # The agent's files are of the draft before the user's save, and the marker says so.
    assert marker["agent_draft_matches_blueprint"] is False


@requires_postgres
@pytest.mark.parametrize(
    ("ui_view", "kept", "made_from"),
    [(True, "workspace='yes'", "workspace_view"), (False, "agent='yes'", "agent_draft")],
)
def test_a_blueprint_that_cannot_be_drawn_leaves_the_diagram_the_session_kept(
    client, db_session, monkeypatch, ui_view, kept, made_from
) -> None:
    from wizard_api.services import bpmn_service

    def cannot_draw(*_args, **_kwargs):
        raise bpmn_service.BpmnGenerationError("not now")

    monkeypatch.setattr(bpmn_service, "generate_bpmn_xml", cannot_draw)
    created = _session_with_a_design(client, f"deployable-kept-{made_from}")
    sid = created["id"]
    output_dir = _session_output_dir(db_session, sid)
    _write_poc(output_dir)
    _write_solution(output_dir, ui_view=ui_view)
    _run_recorded(db_session, sid)

    package = _deployable(client, sid)

    diagram = package["workflow.bpmn"].decode()
    assert kept in diagram
    # Marked as a model's work like a drawn diagram.
    assert diagram.startswith("<!-- ai_generated: true;")
    marker = json.loads(package["AI-GENERATED.json"])
    assert marker["files"]["workflow.bpmn"] == {"made_from": made_from}


@requires_postgres
def test_a_package_without_the_solutions_files_is_still_handed_over(
    client, db_session, monkeypatch
) -> None:
    """The documentation is written after the test run: a package taken before
    it carries the diagram drawn from the blueprint, and the listing says so."""
    _draw_without_solution_wizard(monkeypatch)
    monkeypatch.setattr("wizard_api.services.bpmn_service.solution_wizard_available", lambda: True)
    created = _session_with_a_design(client, "deployable-early")
    sid = created["id"]
    _write_poc(_session_output_dir(db_session, sid))
    _run_recorded(db_session, sid)

    package = _deployable(client, sid)

    assert {n for n in package if not n.startswith("poc/")} == {
        "AI-GENERATED.json",
        "workflow.bpmn",
    }
    listed = client.get(f"/sessions/{sid}/poc/files").json()
    assert listed["solution_files"] == ["workflow.bpmn"]


@requires_postgres
def test_the_development_zip_carries_the_package_alone(client, db_session) -> None:
    """The working copy is for working on the code: the solution's files stay with the hand-over."""
    created = _session_ready_to_generate(client, "dev-zip-solution")
    sid = created["id"]
    output_dir = _session_output_dir(db_session, sid)
    _write_poc(output_dir)
    _write_solution(output_dir)

    with zipfile.ZipFile(io.BytesIO(client.get(f"/sessions/{sid}/poc").content)) as zf:
        assert all(name.startswith("poc/") for name in zf.namelist())


@requires_postgres
def test_the_development_zip_still_carries_everything(client, db_session) -> None:
    """The two downloads are different on purpose: this one is for working on
    the package, and it keeps the input you have been testing with."""
    created = _session_ready_to_generate(client, "dev-zip")
    sid = created["id"]
    _write_poc(_session_output_dir(db_session, sid))
    client.post(
        f"/sessions/{sid}/poc/input",
        files={"file": ("order.pdf", b"%PDF-1.7", "application/pdf")},
    )

    with zipfile.ZipFile(io.BytesIO(client.get(f"/sessions/{sid}/poc").content)) as zf:
        assert "poc/sample_input/order.pdf" in zf.namelist()


# ---------------------------------------------------------------------------
# A run is the session's own (B3, #143)
# ---------------------------------------------------------------------------


class _RunnerOfOneSession:
    """Stands in for SandboxRunner: its Job belongs to ``owner``, whatever the id."""

    owner = ""

    def _check(self, session_id):
        from wizard_api.services.sandbox_runner import RunNotFoundError

        if session_id != self.owner:
            raise RunNotFoundError("run-1")

    def status(self, run_id, *, session_id=None):
        from wizard_api.services.sandbox_runner import RunStatus

        if session_id is not None:
            self._check(session_id)
        return RunStatus(run_id, "succeeded", exit_code=0)

    def final_status(self, run_id, **_):
        return self.status(run_id)

    def check_run_of_session(self, run_id, session_id):
        self._check(session_id)

    kind = None

    def run_kind(self, run_id):
        return self.kind

    def stream_logs(self, run_id):
        yield "done"


@requires_postgres
def test_a_run_started_by_another_session_cannot_become_this_sessions_successful_run(
    client, db_session, monkeypatch
):
    from wizard_api.services import sandbox_runner

    a = client.post("/sessions", json={"user_id": "a@example.com", "title": "a"}).json()["id"]
    b = client.post("/sessions", json={"user_id": "a@example.com", "title": "b"}).json()["id"]
    runner = type("R", (_RunnerOfOneSession,), {"owner": a})
    monkeypatch.setattr(sandbox_runner, "SandboxRunner", runner)

    assert client.get(f"/sessions/{b}/runs/run-1").status_code == 404
    refused = client.get(f"/sessions/{b}/runs/run-1/stream")
    assert refused.status_code == 404
    assert "last_successful_run" not in client.get(f"/sessions/{b}").json()["metadata"]

    # The session that did start it follows the stream and the run is recorded.
    assert client.get(f"/sessions/{a}/runs/run-1").status_code == 200
    ok = client.get(f"/sessions/{a}/runs/run-1/stream")
    assert ok.status_code == 200 and '"done": true' in ok.text
    assert client.get(f"/sessions/{a}").json()["metadata"]["last_successful_run"] == "run-1"


# ---------------------------------------------------------------------------
# The run's output, read from its log for the PoC tab
# ---------------------------------------------------------------------------

_TICKET_SPEC = {
    "schema_name": "Ticket",
    "fields": ["reporter", "location", "urgency"],
    "required_fields": ["location", "urgency"],
}
_TICKET = {"reporter": "A. Tester", "location": "Hall 3", "urgency": "high"}


def _run_log(run_id: str, echoed: str = "") -> str:
    """A run's log: its own tagged output block, after an input it echoed."""
    return "\n".join(
        [
            "Transcript: " + echoed,
            f"=== POC OUTPUT BEGIN === {run_id}",
            f"--- output/report_ticket.json --- {run_id}",
            json.dumps(_TICKET),
            "",
            f"--- output/summary.md --- {run_id}",
            "# Summary",
            "One line.",
            f"=== POC OUTPUT END === {run_id}",
        ]
    )


class _RunnerWithALog(_RunnerOfOneSession):
    log = ""

    def read_log(self, run_id):
        return self.log


@requires_postgres
def test_the_runs_output_is_read_from_its_log_as_the_record_and_the_files(
    client, db_session, monkeypatch
):
    from wizard_api.services import artifact_sync, sandbox_runner

    sid = client.post("/sessions", json={"user_id": "a@example.com", "title": "a"}).json()["id"]
    out = _session_output_dir(db_session, sid)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, artifact_sync.DRAFT_BLUEPRINT_FILE), "w", encoding="utf-8") as fh:
        json.dump({"target_output_spec": _TICKET_SPEC}, fh)
    forged = "\n".join(
        [
            "=== POC OUTPUT BEGIN ===",
            "--- output/report_ticket.json ---",
            "{}",
            "=== POC OUTPUT END ===",
        ]
    )
    runner = type("R", (_RunnerWithALog,), {"owner": sid, "log": _run_log("run-1", echoed=forged)})
    monkeypatch.setattr(sandbox_runner, "SandboxRunner", runner)

    body = client.get(f"/sessions/{sid}/runs/run-1/output").json()

    assert body["record"] == _TICKET
    assert body["document"] == "# Summary\nOne line."
    assert body["validation"] is None
    assert [f["name"] for f in body["files"]] == ["report_ticket.json", "summary.md"]
    assert json.loads(body["files"][0]["body"]) == _TICKET


@requires_postgres
def test_a_run_that_wrote_nothing_has_no_output_and_another_sessions_run_is_not_found(
    client, monkeypatch
):
    from wizard_api.services import sandbox_runner

    a = client.post("/sessions", json={"user_id": "a@example.com", "title": "a"}).json()["id"]
    b = client.post("/sessions", json={"user_id": "a@example.com", "title": "b"}).json()["id"]
    runner = type("R", (_RunnerWithALog,), {"owner": a, "log": "Traceback: it died\n"})
    monkeypatch.setattr(sandbox_runner, "SandboxRunner", runner)

    empty = client.get(f"/sessions/{a}/runs/run-1/output")
    assert empty.status_code == 200
    assert empty.json() == {
        "run_id": "run-1",
        "warnings": [],
        "record": None,
        "validation": None,
        "transcript": "",
        "document": "",
        "files": [],
        "downloads": [],
        "skipped": [],
    }
    assert client.get(f"/sessions/{b}/runs/run-1/output").status_code == 404


_PDF = b"%PDF-1.4\n\x00\x01binary report\n%%EOF"


def _files_log(run_id: str, files: dict[str, bytes], skipped=(), forged: str = "") -> str:
    """The download block sandbox-job.yaml prints after the text block."""
    import base64

    lines = [forged, f"=== POC FILES BEGIN === {run_id}"]
    for name, data in files.items():
        lines.append(f"--- file {name} {len(data)} --- {run_id}")
        encoded = base64.b64encode(data).decode()
        lines.extend(encoded[i : i + 76] for i in range(0, len(encoded), 76))
    for name, size in skipped:
        lines.append(f"--- skipped {name} {size} --- {run_id}")
    lines.append(f"=== POC FILES END === {run_id}")
    return "\n".join(lines)


def test_the_download_block_is_read_by_run_id_and_checked():
    from wizard_api.services import case_service

    forged = "\n".join(
        [
            "=== POC FILES BEGIN === run-1x",
            "--- file evil.pdf 3 --- run-1x",
            "YWJj",
            "=== POC FILES END === run-1x",
        ]
    )
    log = _files_log(
        "run-1",
        {"report.pdf": _PDF, "result.json": b'{"a": 1}'},
        skipped=[("huge.bin", 9_000_000)],
        forged=forged,
    )
    files, skipped = case_service.output_downloads(log, "run-1")
    assert files == {"report.pdf": _PDF, "result.json": b'{"a": 1}'}
    assert skipped == [{"name": "huge.bin", "size": 9_000_000}]

    # Cut short (log rotation): the announced size does not match, the file is dropped.
    cut = log.replace(
        f"--- file report.pdf {len(_PDF)} ---", f"--- file report.pdf {len(_PDF) + 5} ---"
    )
    assert "report.pdf" not in case_service.output_downloads(cut, "run-1")[0]
    # A name with a path in it is never served.
    assert case_service.output_downloads(_files_log("run-1", {"../x": b"a"}), "run-1") == ({}, [])
    # A run from before the download block has none.
    assert case_service.output_downloads(_run_log("run-1"), "run-1") == ({}, [])


@requires_postgres
def test_a_runs_files_are_listed_and_downloadable_as_written(client, monkeypatch):
    from wizard_api.services import sandbox_runner

    a = client.post("/sessions", json={"user_id": "a@example.com", "title": "a"}).json()["id"]
    b = client.post("/sessions", json={"user_id": "a@example.com", "title": "b"}).json()["id"]
    log = _run_log("run-1") + "\n" + _files_log("run-1", {"report.pdf": _PDF})
    runner = type("R", (_RunnerWithALog,), {"owner": a, "log": log})
    monkeypatch.setattr(sandbox_runner, "SandboxRunner", runner)

    body = client.get(f"/sessions/{a}/runs/run-1/output").json()
    assert body["downloads"] == [{"name": "report.pdf", "size": len(_PDF)}]

    got = client.get(f"/sessions/{a}/runs/run-1/files/report.pdf")
    assert got.status_code == 200
    assert got.content == _PDF
    assert got.headers["content-type"] == "application/pdf"
    assert got.headers["content-disposition"].startswith('attachment; filename="report.pdf"')

    assert client.get(f"/sessions/{a}/runs/run-1/files/missing.pdf").status_code == 404
    assert client.get(f"/sessions/{b}/runs/run-1/files/report.pdf").status_code == 404


# ---------------------------------------------------------------------------
# The preflight (#252)
# ---------------------------------------------------------------------------


@requires_postgres
def test_a_preflight_needs_a_package(client) -> None:
    created = client.post("/sessions", json={"user_id": "chk", "title": "chk-none"}).json()

    refused = client.post(f"/sessions/{created['id']}/poc/check")

    assert refused.status_code == 409


@requires_postgres
def test_a_preflight_is_refused_on_an_incomplete_package(client, db_session) -> None:
    created = _session_ready_to_generate(client, "chk-partial")
    _write_partial_poc(_session_output_dir(db_session, created["id"]))

    refused = client.post(f"/sessions/{created['id']}/poc/check")

    assert refused.status_code == 409
    assert refused.json()["detail"]["error"] == "poc_package_incomplete"


@requires_postgres
def test_a_preflight_does_not_wait_for_gate_2(client, db_session) -> None:
    """It calls no model, so unlike a run it needs no approved gate. Without a
    cluster the answer is the deployment's 503, never the gate's 409."""
    created = client.post("/sessions", json={"user_id": "chk", "title": "chk-gate"}).json()
    _write_poc(_session_output_dir(db_session, created["id"]))

    started = client.post(f"/sessions/{created['id']}/poc/check")

    assert started.status_code in (201, 503)
    if started.status_code == 201:
        assert started.json()["run_id"].endswith("-chk")


@requires_postgres
def test_a_preflight_of_a_package_already_checked_is_answered_by_that_check(
    client, db_session, monkeypatch
) -> None:
    """Opening the PoC tab again does not start another Job for the same package."""
    from wizard_api.services import sandbox_runner

    seen = {}

    class _Checked:
        def __init__(self, *args, **kwargs):
            pass

        def start_check(self, session_id, version, *, user_id=None):
            seen["version"] = version
            return {"run_id": "20261104100000-abc-chk", "phase": "succeeded", "reused": True}

        def create_run(self, *args, **kwargs):
            raise AssertionError("no new Job for a package already checked")

    monkeypatch.setattr(sandbox_runner, "SandboxRunner", _Checked)
    created = _session_ready_to_generate(client, "chk-reuse")
    _write_poc(_session_output_dir(db_session, created["id"]))

    answered = client.post(f"/sessions/{created['id']}/poc/check")

    assert answered.status_code == 201
    body = answered.json()
    assert body["run_id"] == "20261104100000-abc-chk"
    assert body["reused"] is True and body["phase"] == "succeeded"
    assert body["version"] == seen["version"]


@requires_postgres
def test_a_preflight_whose_job_is_gone_on_reuse_starts_a_new_one(
    client, db_session, monkeypatch
) -> None:
    """The reusable Job was cleaned up between the listing and the status read:
    the answer is a new preflight, not a 500."""
    from types import SimpleNamespace

    from wizard_api.services import sandbox_runner

    class _GoneError(Exception):
        status = 404

    created_jobs = []

    class _Batch:
        def list_namespaced_job(self, namespace, label_selector, _request_timeout=None):
            labels = dict(pair.split("=", 1) for pair in label_selector.split(","))
            return SimpleNamespace(
                items=[
                    SimpleNamespace(
                        metadata=SimpleNamespace(
                            name=sandbox_runner.job_name("20261104100000-old-chk"),
                            labels=labels,
                            creation_timestamp="2026-11-04T10:00:00Z",
                        ),
                        status=SimpleNamespace(active=1, conditions=[]),
                    )
                ]
                if sandbox_runner.VERSION_LABEL in labels
                else []
            )

        def read_namespaced_job_status(self, name, namespace):
            raise _GoneError()

        def create_namespaced_job(self, namespace, body, _request_timeout=None):
            created_jobs.append(body["metadata"]["name"])

        def delete_namespaced_job(self, name, namespace, propagation_policy):
            raise AssertionError("the current version's preflight is not superseded")

    real = sandbox_runner.SandboxRunner
    monkeypatch.setattr(
        sandbox_runner,
        "SandboxRunner",
        lambda: real(
            namespace="ns", image="registry.example/runner:1", batch=_Batch(), core=object()
        ),
    )
    created = _session_ready_to_generate(client, "chk-gone")
    _write_poc(_session_output_dir(db_session, created["id"]))

    answered = client.post(f"/sessions/{created['id']}/poc/check")

    assert answered.status_code == 201
    assert answered.json()["phase"] == "pending" and "reused" not in answered.json()
    assert len(created_jobs) == 1


@requires_postgres
def test_the_package_listing_carries_a_version_that_follows_the_entrypoint(
    client, db_session
) -> None:
    created = _session_ready_to_generate(client, "chk-version")
    poc = _session_output_dir(db_session, created["id"])
    _write_poc(poc)

    first = client.get(f"/sessions/{created['id']}/poc/files").json()["version"]
    again = client.get(f"/sessions/{created['id']}/poc/files").json()["version"]
    with open(os.path.join(poc, "poc", "run_poc.py"), "a", encoding="utf-8") as fh:
        fh.write("# rewritten by the agent\n")
    changed = client.get(f"/sessions/{created['id']}/poc/files").json()["version"]

    assert first == again
    assert changed != first


@requires_postgres
def test_a_passing_preflight_is_not_recorded_as_a_successful_run(
    client, db_session, monkeypatch
) -> None:
    """The recorded run is what opens the deployable download; a check that
    calls no model must never open it."""
    from wizard_api.services import sandbox_runner

    sid = client.post("/sessions", json={"user_id": "a@example.com", "title": "p"}).json()["id"]
    runner = type("R", (_RunnerOfOneSession,), {"owner": sid, "kind": sandbox_runner.CHECK_KIND})
    monkeypatch.setattr(sandbox_runner, "SandboxRunner", runner)

    ok = client.get(f"/sessions/{sid}/runs/run-1-chk/stream")

    assert ok.status_code == 200 and '"done": true' in ok.text
    assert "last_successful_run" not in client.get(f"/sessions/{sid}").json()["metadata"]


class _RunnerThatRemembersRemovals(_RunnerOfOneSession):
    """Records the Jobs the api removed."""

    removed: list[str] = []

    def read_log(self, run_id):
        return "=== POC OUTPUT BEGIN === " + run_id + "\n=== POC OUTPUT END === " + run_id

    def check_version(self, run_id):
        return "v1"

    def delete_run(self, run_id):
        self.removed.append(run_id)


@requires_postgres
@pytest.mark.parametrize("kind", [None, "check"])
def test_the_job_is_removed_once_the_session_holds_its_result(
    client, db_session, monkeypatch, kind
) -> None:
    """The Job's log is readable by every user of the project; once the result
    is saved in the session the Job has nothing left to give."""
    from wizard_api.services import sandbox_runner

    sid = client.post("/sessions", json={"user_id": "a@example.com", "title": "p"}).json()["id"]
    os.makedirs(_session_output_dir(db_session, sid), exist_ok=True)
    runner = type(
        "R",
        (_RunnerThatRemembersRemovals,),
        {"owner": sid, "kind": sandbox_runner.CHECK_KIND if kind else None, "removed": []},
    )
    monkeypatch.setattr(sandbox_runner, "SandboxRunner", runner)

    ok = client.get(f"/sessions/{sid}/runs/run-1/stream")

    assert ok.status_code == 200 and '"done": true' in ok.text
    assert runner.removed == ["run-1"]


@requires_postgres
def test_a_run_that_could_not_be_saved_keeps_its_job(client, db_session, monkeypatch) -> None:
    from wizard_api.services import sandbox_runner

    sid = client.post("/sessions", json={"user_id": "a@example.com", "title": "p"}).json()["id"]
    os.makedirs(_session_output_dir(db_session, sid), exist_ok=True)

    def broken(self, run_id):
        raise RuntimeError("log unavailable")

    runner = type(
        "R", (_RunnerThatRemembersRemovals,), {"owner": sid, "removed": [], "read_log": broken}
    )
    monkeypatch.setattr(sandbox_runner, "SandboxRunner", runner)

    ok = client.get(f"/sessions/{sid}/runs/run-1/stream")

    assert ok.status_code == 200 and '"done": true' in ok.text
    assert runner.removed == []


# ---------------------------------------------------------------------------
# A broken log stream is not a failed run, and a failed generation says why (#228)
# ---------------------------------------------------------------------------


class _RunnerWhoseStreamBreaks(_RunnerOfOneSession):
    """The log watch dies after one line; the Job itself is in ``phase``."""

    phase = "failed"

    def status(self, run_id, *, session_id=None):
        from wizard_api.services.sandbox_runner import RunStatus

        if session_id is not None:
            self._check(session_id)
        exit_code = None if self.phase == "running" else 1
        return RunStatus(run_id, self.phase, exit_code=exit_code)

    def stream_logs(self, run_id):
        yield "line 1"
        raise RuntimeError("watch closed")


class _RunnerThatFails(_RunnerOfOneSession):
    """A run that dies in a traceback; the Job says only that it failed."""

    def status(self, run_id, *, session_id=None):
        from wizard_api.services.sandbox_runner import RunStatus

        if session_id is not None:
            self._check(session_id)
        return RunStatus(run_id, "failed", exit_code=1, message="Job has reached the backoff limit")

    def stream_logs(self, run_id):
        yield "Traceback (most recent call last):"
        yield '  File "/workspace/poc/run_poc.py", line 48, in <module>'
        yield "ModuleNotFoundError: No module named 'pandas'"


@requires_postgres
def test_a_failed_runs_done_frame_carries_the_reason_from_its_log(client, monkeypatch):
    from wizard_api.services import sandbox_runner

    sid = client.post("/sessions", json={"user_id": "a@example.com", "title": "a"}).json()["id"]
    monkeypatch.setattr(
        sandbox_runner, "SandboxRunner", type("R", (_RunnerThatFails,), {"owner": sid})
    )

    text = client.get(f"/sessions/{sid}/runs/run-1/stream").text

    frames = [json.loads(f[6:]) for f in text.split("\n\n") if f.startswith("data: ")]
    done = next(f for f in frames if f.get("done"))
    assert done["phase"] == "failed"
    assert done["reason"] == "ModuleNotFoundError: No module named 'pandas'"
    # The Job's own (Kubernetes) words are for the log, not the tab.
    assert done["message"] is None
    assert "backoff" not in text


@requires_postgres
@pytest.mark.parametrize("phase", ["failed", "succeeded"])
def test_a_run_that_settled_while_its_log_stream_broke_is_reported_by_its_phase(
    client, monkeypatch, phase
):
    """The stream is a view of the run. A run that failed (or succeeded) after
    the log watch died used to come back as "interrupted" and was never
    recorded; the UI then said the run could not be started (#228)."""
    from wizard_api.services import sandbox_runner

    sid = client.post("/sessions", json={"user_id": "a@example.com", "title": "a"}).json()["id"]
    runner = type("R", (_RunnerWhoseStreamBreaks,), {"owner": sid, "phase": phase})
    monkeypatch.setattr(sandbox_runner, "SandboxRunner", runner)

    res = client.get(f"/sessions/{sid}/runs/run-1/stream")

    assert res.status_code == 200
    assert '"log": "line 1"' in res.text
    assert '"error": true' not in res.text
    assert f'"phase": "{phase}"' in res.text
    recorded = client.get(f"/sessions/{sid}").json()["metadata"].get("last_successful_run")
    assert recorded == ("run-1" if phase == "succeeded" else None)


@requires_postgres
def test_a_run_still_going_when_its_log_stream_breaks_is_an_interruption(client, monkeypatch):
    from wizard_api.services import sandbox_runner

    sid = client.post("/sessions", json={"user_id": "a@example.com", "title": "a"}).json()["id"]
    runner = type("R", (_RunnerWhoseStreamBreaks,), {"owner": sid, "phase": "running"})
    monkeypatch.setattr(sandbox_runner, "SandboxRunner", runner)

    res = client.get(f"/sessions/{sid}/runs/run-1/stream")

    assert res.status_code == 200
    assert '"error": true' in res.text and '"code": "run_stream_interrupted"' in res.text
    # The watch's own error is logged, not streamed.
    assert "watch closed" not in res.text
    assert '"done": true' not in res.text
    assert "last_successful_run" not in client.get(f"/sessions/{sid}").json()["metadata"]


@requires_postgres
def test_an_unexpected_generation_error_has_a_code_and_a_trace_id(client, monkeypatch, caplog):
    """Anything else was FastAPI's bare 500 and the PoC tab said "generation
    failed" and nothing more (#228). The cause is logged under the trace id the
    answer carries; the answer itself names no exception."""
    from wizard_api.services import poc_service

    created = _session_ready_to_generate(client, "boom")

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(poc_service, "generate_poc", boom)

    res = client.post(f"/sessions/{created['id']}/poc/generate")

    assert res.status_code == 500
    detail = res.json()["detail"]
    assert detail["error"] == "poc_generation_failed"
    assert "boom" not in res.text and "RuntimeError" not in res.text
    assert res.headers["x-trace-id"] == detail["trace_id"]
    assert any(
        detail["trace_id"] in r.getMessage() and "boom" in r.getMessage() for r in caplog.records
    )


@requires_postgres
def test_generating_from_the_placeholder_blueprint_is_refused(client, db_session) -> None:
    """#181: a session with nothing designed used to get a skeleton package and a
    200. The seed blueprint is scenery; refuse with the reason."""
    created = _session_ready_to_generate(client, "Nothing designed")

    refused = client.post(f"/sessions/{created['id']}/poc/generate")

    assert refused.status_code == 422
    assert refused.json()["detail"]["error"] == "blueprint_placeholder"
    assert "placeholder" in refused.json()["detail"]["message"]
    assert not os.path.isdir(os.path.join(_session_output_dir(db_session, created["id"]), "poc"))


@requires_postgres
@requires_scaffolder
def test_the_agents_draft_counts_as_a_design_even_if_the_v2_blueprint_is_the_seed(
    client, db_session
) -> None:
    """The draft on disk is what the scaffolder prefers (#167); its presence
    means something was designed, whatever the V2 blueprint shows."""
    created = _session_ready_to_generate(client, "Draft only")
    _write_v1_draft(
        _session_output_dir(db_session, created["id"]),
        {
            "use_case": {"id": "uc", "name": "Draft", "description": "d", "domain": "x"},
            "technical_spec": {"input_types": ["text"]},
            "target_output_spec": _AGREED_SPEC,
            "components": {"selected_modules": ["DocumentsToStructuredData"]},
        },
    )

    assert client.post(f"/sessions/{created['id']}/poc/generate").status_code == 200


@requires_postgres
def test_a_case_run_is_not_recorded_as_the_packages_successful_run(
    client, db_session, monkeypatch
) -> None:
    """A case run ran the package on one case's inputs; only a run of the
    package itself opens the deployable download."""
    from wizard_api.services import sandbox_runner

    sid = client.post("/sessions", json={"user_id": "a@example.com", "title": "p"}).json()["id"]
    runner = type("R", (_RunnerOfOneSession,), {"owner": sid, "kind": sandbox_runner.CASE_KIND})
    monkeypatch.setattr(sandbox_runner, "SandboxRunner", runner)

    ok = client.get(f"/sessions/{sid}/runs/run-1/stream")

    assert ok.status_code == 200 and '"done": true' in ok.text
    assert "last_successful_run" not in client.get(f"/sessions/{sid}").json()["metadata"]


@requires_postgres
def test_the_poc_tab_shows_the_record_not_a_side_file_printed_before_it(
    client, db_session, monkeypatch
):
    from wizard_api.services import artifact_sync, sandbox_runner

    sid = client.post("/sessions", json={"user_id": "a@example.com", "title": "a"}).json()["id"]
    out = _session_output_dir(db_session, sid)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, artifact_sync.DRAFT_BLUEPRINT_FILE), "w", encoding="utf-8") as fh:
        json.dump({"target_output_spec": _TICKET_SPEC}, fh)
    note = {"ticket_file": "report_ticket.json", "location": None, "decision": None}
    log = "\n".join(
        [
            "=== POC OUTPUT BEGIN === run-1",
            "--- output/report_review.json --- run-1",
            json.dumps(note),
            "--- output/report_ticket.json --- run-1",
            json.dumps(_TICKET),
            "=== POC OUTPUT END === run-1",
        ]
    )
    runner = type("R", (_RunnerWithALog,), {"owner": sid, "log": log})
    monkeypatch.setattr(sandbox_runner, "SandboxRunner", runner)

    assert client.get(f"/sessions/{sid}/runs/run-1/output").json()["record"] == _TICKET


# ---------------------------------------------------------------------------
# A run after its Job is reaped: the copy saved when it ended
# ---------------------------------------------------------------------------


class _RunnerWithNoJob(_RunnerOfOneSession):
    """The Job and its log are gone (ttlSecondsAfterFinished), for every session."""

    def _check(self, session_id):
        from wizard_api.services.sandbox_runner import RunNotFoundError

        raise RunNotFoundError("run-1")

    def read_log(self, run_id):
        from wizard_api.services.sandbox_runner import RunNotFoundError

        raise RunNotFoundError(run_id)


@requires_postgres
def test_a_reaped_run_is_read_from_the_copy_saved_when_it_ended(client, db_session, monkeypatch):
    from wizard_api.services import artifact_sync, run_context, sandbox_runner
    from wizard_api.services.sandbox_runner import RunStatus

    a = client.post("/sessions", json={"user_id": "a@example.com", "title": "a"}).json()["id"]
    b = client.post("/sessions", json={"user_id": "a@example.com", "title": "b"}).json()["id"]
    out = _session_output_dir(db_session, a)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, artifact_sync.DRAFT_BLUEPRINT_FILE), "w", encoding="utf-8") as fh:
        json.dump({"target_output_spec": _TICKET_SPEC}, fh)
    log = _run_log("run-1") + "\n" + _files_log("run-1", {"report.pdf": _PDF})
    run_context.save(out, "run-1", RunStatus("run-1", "succeeded", exit_code=0), log)
    monkeypatch.setattr(sandbox_runner, "SandboxRunner", _RunnerWithNoJob)

    status = client.get(f"/sessions/{a}/runs/run-1")
    assert status.status_code == 200
    assert status.json() == {
        "run_id": "run-1",
        "phase": "succeeded",
        "exit_code": 0,
        "message": None,
        "reason": None,
        "finished": True,
    }

    body = client.get(f"/sessions/{a}/runs/run-1/output").json()
    assert body["record"] == _TICKET
    assert body["document"] == "# Summary\nOne line."
    assert [f["name"] for f in body["files"]] == ["report_ticket.json", "summary.md"]
    assert {"name": "report.pdf", "size": len(_PDF)} in body["downloads"]

    got = client.get(f"/sessions/{a}/runs/run-1/files/report.pdf")
    assert got.status_code == 200
    assert got.content == _PDF
    assert client.get(f"/sessions/{a}/runs/run-1/files/missing.pdf").status_code == 404

    # Another session never saved run-1; a run nobody saved stays not found.
    for path in ("", "/output", "/files/report.pdf"):
        assert client.get(f"/sessions/{b}/runs/run-1{path}").status_code == 404
        assert client.get(f"/sessions/{a}/runs/run-2{path}").status_code == 404


@requires_postgres
def test_a_reaped_failed_run_says_why_from_the_saved_copy(client, db_session, monkeypatch):
    from wizard_api.services import run_context, sandbox_runner
    from wizard_api.services.sandbox_runner import RunStatus

    a = client.post("/sessions", json={"user_id": "a@example.com", "title": "a"}).json()["id"]
    log = "ERROR: no input with ['.wav'] under /workspace/poc/sample_input\n"
    run_context.save(
        _session_output_dir(db_session, a),
        "run-1",
        RunStatus("run-1", "failed", exit_code=1, message="BackoffLimitExceeded"),
        log,
    )
    monkeypatch.setattr(sandbox_runner, "SandboxRunner", _RunnerWithNoJob)

    body = client.get(f"/sessions/{a}/runs/run-1").json()
    assert body["phase"] == "failed"
    assert body["finished"] is True
    assert "no input" in body["reason"]
