"""Marks what the wizard hands out as AI-generated, in a form a machine can read.

A package or a session copy carries ``AI-GENERATED.json``, a download carries two
headers, and the BPMN diagram opens with a comment. The deployable package has one
marker in ``poc/`` and one at its root for the files beside it. The
marker is written when the package is handed out, over any file of that name the
package holds, so what it says comes from this service and not from the session.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

from wizard_api.services import agent_service

MARKER_FILE = "AI-GENERATED.json"
GENERATOR = "GAIK Solution Wizard"
SCHEMA = "gaik.ai-generated/1"
#: The IPTC term for content made by a trained model.
DIGITAL_SOURCE_TYPE = "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"


def model() -> str:
    """The model this deployment's agent uses."""
    return agent_service.agent_model()


def marker(session: Any, content: str, now: datetime | None = None) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "ai_generated": True,
        "digital_source_type": DIGITAL_SOURCE_TYPE,
        "generator": GENERATOR,
        "generator_version": os.getenv("APP_VERSION", "dev"),
        "model": model(),
        "content": content,
        "session_id": str(session.id),
        "blueprint_version": session.active_version,
        "exported_at": (now or datetime.now(UTC)).isoformat(timespec="seconds"),
    }


def marker_json(session: Any, content: str, **extra: Any) -> str:
    """The marker as the file holds it; ``extra`` adds fields after the standard ones."""
    return json.dumps({**marker(session, content), **extra}, indent=2) + "\n"


def headers() -> dict[str, str]:
    return {"X-AI-Generated": "true", "X-AI-Model": model()}


#: How the diagram's comment starts; a diagram that has it is marked already.
_XML_MARK = "<!-- ai_generated: true;"


def mark_xml(xml: str) -> str:
    """The diagram with a comment after its declaration that says a model made it.

    A comment, not an element: every BPMN reader keeps the file valid, and a
    person who opens the file sees the line first. A diagram marked already,
    such as one the session kept, is returned as it is.
    """
    if _XML_MARK in xml:
        return xml
    comment = f"{_XML_MARK} generator: {GENERATOR}; model: {model()} -->"
    head, sep, tail = xml.partition("?>")
    if sep:
        return f"{head}{sep}\n{comment}{tail}"
    return f"{comment}\n{xml}"
