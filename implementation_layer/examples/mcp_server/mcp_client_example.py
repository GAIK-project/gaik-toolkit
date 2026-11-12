"""MCP Server Example

Starts the GAIK MCP server over stdio, as an agent would, and uses it with the official MCP
client: lists the tools, reads a text file and builds a Word file. No credentials are needed,
because these two tools call no model.

Run it with the `mcp` extra installed: pip install "gaik[mcp]"
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).parent.parent.parent / "src"

# Allow running without `pip install -e .`
sys.path.insert(0, str(SRC))

from mcp import Client, StdioServerParameters  # noqa: E402

# Synthetic: no real site, person or order.
NOTE = (
    "Service visit at Hall 3 on 12 November 2026.\n"
    "The technician replaced the inlet valve of pump P-204.\n"
    "The pump was tested for 30 minutes without leaks.\n"
)


def server_command(root: Path) -> StdioServerParameters:
    """The command an agent's configuration would hold: `gaik-mcp --root <folder>`."""
    paths = [str(SRC), os.environ.get("PYTHONPATH", "")]
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "gaik.mcp_server", "--root", str(root)],
        env={**os.environ, "PYTHONPATH": os.pathsep.join(path for path in paths if path)},
    )


async def list_parse_and_write(root: Path) -> None:
    """List the tools, parse `note.txt` and write `reports/service_report.docx`."""
    (root / "note.txt").write_text(NOTE, encoding="utf-8")

    async with Client(server_command(root)) as client:
        listed = await client.list_tools()
        print("Tools:", ", ".join(tool.name for tool in listed.tools))

        parsed = await client.call_tool("parse_document", {"path": "note.txt"})
        document = parsed.structured_content
        print(f"Parsed a {document['format']} file of {document['total_chars']} characters")

        # With provider credentials, `extract_fields` would fill these from the text:
        #   await client.call_tool("extract_fields", {"text": document["text"],
        #       "requirement": "The site, the date and the work done."})
        fields = [
            {"label": "Site", "value": "Hall 3", "evidence": "Hall 3", "verdict": "verified"},
            {"label": "Visit date", "value": "2026-11-12", "evidence": "12 November 2026"},
            {"label": "Follow-up needed", "value": False},
        ]
        written = await client.call_tool(
            "fields_to_word",
            {
                "fields": fields,
                "title": "Service report",
                "metadata": {"Source": "note.txt"},
                "appendix": document["text"],
                "output_path": "reports/service_report.docx",
            },
        )
        report = written.structured_content
        print(f"Wrote {root / report['path']} ({report['bytes']} bytes, {report['rows']} rows)")

        refused = await client.call_tool("parse_document", {"path": "../outside.txt"})
        print("A path outside the root:", refused.content[0].text)


if __name__ == "__main__":
    folder = Path(tempfile.mkdtemp(prefix="gaik-mcp-example-")).resolve()
    asyncio.run(list_parse_and_write(folder))
