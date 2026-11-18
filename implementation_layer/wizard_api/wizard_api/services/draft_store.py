"""Write the session's full blueprint draft, and the diagrams derived from it.

``use_case.blueprint.json`` in the session's output folder is the canonical
blueprint: the agent writes it, and the user's diagram and JSON edits write it
too. This module is the one writer the API uses for it. A draft is validated
before anything touches the disk, goes to a temp file in the same folder and
replaces the old file whole, so a reader never sees half a file and a rejected
draft leaves the previous one as it was. A symlink in the draft's place is
refused: it could point the write at a file outside the session.

The draft is written as the dict it was given, not as a re-dump of the model:
the readers (``artifact_sync.read_draft_blueprint`` and the agent's own
scripts) read the raw JSON, and a dump would add every default field and drop
keys the model ignores.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from typing import Any

from wizard_api.services.artifact_sync import (
    DRAFT_BLUEPRINT_FILE,
    WORKFLOW_BPMN_FILE,
    WORKFLOW_MMD_FILE,
    artifact_path,
)

try:
    from solution_wizard.blueprint import Blueprint
    from solution_wizard.bpmn_generator import write_bpmn
    from solution_wizard.visualizer import write_mermaid
except ImportError:  # pragma: no cover - optional in minimal installs
    Blueprint = None  # type: ignore[assignment,misc]
    write_bpmn = write_mermaid = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _require_solution_wizard() -> None:
    if Blueprint is None:
        raise RuntimeError("solution_wizard is not installed")


def write_draft(output_dir: str, blueprint: dict[str, Any]) -> None:
    """Validate ``blueprint`` and write it whole as the session's draft.

    Raises ``pydantic.ValidationError`` for an invalid blueprint and
    ``ValueError`` when the draft's path is a symlink; nothing is written in
    either case.
    """
    _require_solution_wizard()
    Blueprint.model_validate(blueprint)
    target = artifact_path(output_dir, DRAFT_BLUEPRINT_FILE)
    if os.path.islink(target):
        raise ValueError(f"{DRAFT_BLUEPRINT_FILE} is a symlink; refusing to write it")
    text = json.dumps(blueprint, indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(dir=output_dir, prefix=f".{DRAFT_BLUEPRINT_FILE}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def refresh_derived_files(output_dir: str, blueprint: dict[str, Any]) -> None:
    """Rewrite ``workflow.bpmn`` and ``workflow.mmd`` from ``blueprint``.

    Best-effort: a failure is logged and the call returns. A symlink in the
    place of either file is left alone. Each file is generated in a temp
    folder and moved into place, so the writers never follow a link and a
    reader never sees half a diagram.
    """
    try:
        _require_solution_wizard()
        model = Blueprint.model_validate(blueprint)
    except Exception:
        logger.warning("Derived files not refreshed: the blueprint is not valid", exc_info=True)
        return
    for filename, writer in ((WORKFLOW_BPMN_FILE, write_bpmn), (WORKFLOW_MMD_FILE, write_mermaid)):
        target = artifact_path(output_dir, filename)
        if os.path.islink(target):
            logger.warning("%s is a symlink; not refreshing it", filename)
            continue
        tmp_dir = None
        try:
            tmp_dir = tempfile.mkdtemp(dir=output_dir, prefix=".derived.")
            written = writer(model, tmp_dir)
            os.replace(written, target)
        except Exception:
            logger.warning("Could not refresh %s", filename, exc_info=True)
        finally:
            if tmp_dir is not None:
                shutil.rmtree(tmp_dir, ignore_errors=True)
