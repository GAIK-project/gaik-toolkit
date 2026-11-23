"""A copy of what the wizard holds for a session, for the person it belongs to.

``session.json`` has the conversation, gates and every blueprint version;
``files/`` has the session folder as it is. The agent's own working files stay
out: the conversation the person had is in ``session.json``.
"""

from __future__ import annotations

import json
import os
import zipfile
from datetime import UTC, datetime
from typing import Any, BinaryIO

from wizard_api.models import WizardSession
from wizard_api.services import ai_marking, poc_service

#: Bookkeeping of the service, not information about the person.
_INTERNAL_METADATA = frozenset({"agent_sdk_session_id", "agent_seen_run"})
_LEFT_OUT = frozenset({".env", "__pycache__"})


def session_record(session: WizardSession, now: datetime | None = None) -> dict[str, Any]:
    metadata = session.session_metadata
    return {
        "exported_at": (now or datetime.now(UTC)).isoformat(timespec="seconds"),
        "session_id": str(session.id),
        "user_id": session.user_id,
        "step": session.step,
        "gate_statuses": session.gate_statuses,
        "metadata": {k: v for k, v in metadata.items() if k not in _INTERNAL_METADATA},
        "active_version": session.active_version,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "blueprint_versions": [
            {
                "version": version.version,
                "note": version.note,
                "content": version.content,
                "created_at": version.created_at.isoformat(),
            }
            for version in session.blueprint_versions
        ],
    }


def _exported(relative: str) -> bool:
    return not _LEFT_OUT.intersection(relative.split(os.sep))


def write_archive(session: WizardSession, target: BinaryIO) -> None:
    """Write the session as a zip. Real files only, so a link cannot pull one in."""
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        record = json.dumps(session_record(session), indent=2, ensure_ascii=False, default=str)
        archive.writestr("session.json", record)
        # The blueprints and the package in the copy are AI output; say so where
        # a machine reads it, as the package download does.
        archive.writestr(ai_marking.MARKER_FILE, ai_marking.marker_json(session, "session-export"))
        if not os.path.isdir(session.output_dir):
            return
        for relative in poc_service.regular_files(session.output_dir):
            if _exported(relative):
                source = os.path.join(session.output_dir, relative)
                archive.write(source, os.path.join("files", relative))
