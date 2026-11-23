import json
import os

import pytest
from sqlalchemy import create_engine, text
from wizard_api.config import get_database_url


def postgres_available() -> bool:
    try:
        engine = create_engine(get_database_url(), pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


requires_postgres = pytest.mark.skipif(not postgres_available(), reason="Postgres not available")


def write_gate_artifacts(output_dir: str, through: str = "gate_2") -> None:
    """Write what the agent would have produced by ``through``, so the gate can be approved.

    A gate is refused while what it reviews does not exist (artifact_sync.gate_missing):
    the specification for Gate 1, components and the workflow diagram for Gate 2, the
    package for Gate 3. Tests that are about something past a gate start from here.
    """
    os.makedirs(output_dir, exist_ok=True)
    draft = {
        "use_case": {"name": "Test use case"},
        "workflow": {"steps": [{"id": "extract", "name": "Extract", "component": "Extractor"}]},
    }
    with open(os.path.join(output_dir, "use_case.blueprint.json"), "w", encoding="utf-8") as fh:
        json.dump(draft, fh)
    if through in ("gate_2", "gate_3"):
        with open(os.path.join(output_dir, "workflow.bpmn"), "w", encoding="utf-8") as fh:
            fh.write("<definitions/>")
    if through == "gate_3":
        os.makedirs(os.path.join(output_dir, "poc"), exist_ok=True)
        with open(os.path.join(output_dir, "poc", "run_poc.py"), "w", encoding="utf-8") as fh:
            fh.write("print('ok')\n")
