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
from pathlib import Path
from typing import Any

from wizard_api.services.artifact_sync import (
    DRAFT_BLUEPRINT_FILE,
    WORKFLOW_BPMN_FILE,
    WORKFLOW_MMD_FILE,
    artifact_path,
)

try:
    from solution_wizard.blueprint import Blueprint
    from solution_wizard.bpmn_generator import generate_bpmn, write_bpmn
    from solution_wizard.visualizer import write_mermaid
except ImportError:  # pragma: no cover - optional in minimal installs
    Blueprint = None  # type: ignore[assignment,misc]
    generate_bpmn = write_bpmn = write_mermaid = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _require_solution_wizard() -> None:
    if Blueprint is None:
        raise RuntimeError("solution_wizard is not installed")


def validate_draft(blueprint: dict[str, Any]) -> None:
    """Raise ``pydantic.ValidationError`` unless ``blueprint`` is a valid draft:
    the check :func:`write_draft` makes before it writes."""
    _require_solution_wizard()
    Blueprint.model_validate(blueprint)


def write_draft(output_dir: str, blueprint: dict[str, Any]) -> None:
    """Validate ``blueprint`` and write it whole as the session's draft.

    Raises ``pydantic.ValidationError`` for an invalid blueprint and
    ``ValueError`` when the draft's path is a symlink; nothing is written in
    either case.
    """
    validate_draft(blueprint)
    target = artifact_path(output_dir, DRAFT_BLUEPRINT_FILE)
    if os.path.islink(target):
        raise ValueError(f"{DRAFT_BLUEPRINT_FILE} is a symlink; refusing to write it")
    text = json.dumps(blueprint, indent=2, ensure_ascii=False) + "\n"
    _replace(output_dir, DRAFT_BLUEPRINT_FILE, text.encode("utf-8"))


def _replace(output_dir: str, filename: str, data: bytes) -> None:
    """Write ``data`` to a temp file in ``output_dir`` and move it over ``filename``."""
    target = artifact_path(output_dir, filename)
    fd, tmp = tempfile.mkstemp(dir=output_dir, prefix=f".{filename}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


#: The files an edit rewrites: the draft and the diagrams derived from it.
_EDITED_FILES = (DRAFT_BLUEPRINT_FILE, WORKFLOW_BPMN_FILE, WORKFLOW_MMD_FILE)


def snapshot(output_dir: str) -> dict[str, bytes | None]:
    """The draft and its derived files as they are now, for ``restore``.

    ``None`` stands for a file that is not there. A symlink is left out: no
    writer here follows one, so there is nothing to put back.
    """
    taken: dict[str, bytes | None] = {}
    for filename in _EDITED_FILES:
        path = artifact_path(output_dir, filename)
        if os.path.islink(path):
            continue
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            taken[filename] = None
            continue
        with os.fdopen(fd, "rb") as fh:
            taken[filename] = fh.read()
    return taken


def restore(output_dir: str, taken: dict[str, bytes | None]) -> None:
    """Put the files of a ``snapshot`` back as they were, each one best-effort.

    For an edit whose database write failed after its files were written: the
    version history and the files must go on saying the same thing.
    """
    for filename, data in taken.items():
        path = artifact_path(output_dir, filename)
        try:
            if os.path.islink(path):
                continue
            if data is None:
                if os.path.exists(path):
                    os.unlink(path)
            else:
                _replace(output_dir, filename, data)
        except Exception:
            logger.error("Could not put %s back after a failed edit", filename, exc_info=True)


def refresh_derived_files(
    output_dir: str, blueprint: dict[str, Any], *, extra_lane_ids: frozenset[str] = frozenset()
) -> None:
    """Rewrite ``workflow.bpmn`` and ``workflow.mmd`` from ``blueprint``.

    ``extra_lane_ids``: the lanes the user added (``artifact_sync.user_lanes``),
    drawn in ``workflow.bpmn`` also while empty, as the editor shows them.

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

    def bpmn_writer(model: Any, folder: str) -> Path:
        if not extra_lane_ids:
            return write_bpmn(model, folder)
        path = Path(folder) / WORKFLOW_BPMN_FILE
        path.write_text(generate_bpmn(model, extra_lane_ids=extra_lane_ids), encoding="utf-8")
        return path

    for filename, writer in ((WORKFLOW_BPMN_FILE, bpmn_writer), (WORKFLOW_MMD_FILE, write_mermaid)):
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
