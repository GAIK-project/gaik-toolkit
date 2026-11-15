"""Live test of the MCP server: ``extract_fields`` through an in-process client.

The official client calls the tool with two field definitions and a synthetic service note;
the real extractor fills them and the quotes are checked against the note. One model call.

Needs Azure OpenAI: ``AZURE_API_KEY`` and ``AZURE_ENDPOINT``, with ``AZURE_DEPLOYMENT``
naming the chat deployment. Skipped when the key or the endpoint is missing.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest

pytest.importorskip("mcp")

from gaik.mcp_server import ServerSettings, build_server  # noqa: E402
from gaik.operations import OperationSettings  # noqa: E402
from mcp import Client  # noqa: E402

_MISSING = [name for name in ("AZURE_API_KEY", "AZURE_ENDPOINT") if not os.getenv(name, "").strip()]

# Calls a real LLM: these assert on model output, so they fail when the model or
# the Azure deployment changes, not only when our code regresses. Kept out of the
# push gate (`-m "not llm"`); see .github/workflows/test.yml.
pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(bool(_MISSING), reason=f"live Azure OpenAI test: set {', '.join(_MISSING)}"),
]

# Synthetic: no real site, person or order.
NOTE = (
    "Service visit at Hall 3 on 12 November 2026.\n"
    "The technician replaced the inlet valve of pump P-204 and changed two gaskets.\n"
    "The pump was tested for 30 minutes without leaks.\n"
)
FIELDS = [
    {
        "name": "site",
        "description": "The hall or site where the work was done, as the note names it",
    },
    {"name": "Work done", "description": "What the technician did, in one sentence"},
]


def test_extract_fields_returns_values_with_quotes_from_the_note(
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = ServerSettings(operations=OperationSettings(provider="azure"))

    async def scenario() -> Any:
        async with Client(build_server(settings)) as client:
            return await client.call_tool("extract_fields", {"text": NOTE, "fields": FIELDS})

    result = asyncio.run(scenario())

    assert not result.is_error, result.content
    answer = result.structured_content
    assert answer["fields_generated"] is False
    assert [field["name"] for field in answer["fields"]] == ["site", "Work done"]
    values = {item["name"]: item for item in answer["values"]}
    assert list(values) == ["site", "Work done"]
    assert "Hall 3" in values["site"]["value"]
    assert "valve" in values["Work done"]["value"].lower()
    assert (answer["filled"], answer["total"]) == (2, 2)
    for item in values.values():
        assert item["evidence"] and item["evidence"] in NOTE
        assert item["verdict"] in ("verified", "reworded")
    # What the extractor prints stays out of stdout.
    assert capsys.readouterr().out == ""
