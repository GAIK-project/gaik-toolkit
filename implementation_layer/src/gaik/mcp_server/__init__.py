"""GAIK MCP server

The functions of ``gaik.operations`` and ``FieldsToDocx`` as tools for agents, over stdio or
Streamable HTTP with a bearer token. Start it with the console script ``gaik-mcp`` or with
``python -m gaik.mcp_server``.

Main names:
    - build_server: an ``MCPServer`` with the six tools, from ``ServerSettings``
    - ServerSettings: the allowed folder, the size limits and the model settings

Tools:
    parse_document, transcribe_audio, generate_fields, extract_fields, classify_text,
    fields_to_word

Example:
    >>> from gaik.mcp_server import ServerSettings, build_server
    >>> server = build_server(ServerSettings(root=None))
    >>> server.run(transport="stdio")

Importing this package loads neither the MCP SDK nor a gaik component: the SDK is needed
only by ``build_server`` (``pip install "gaik[mcp]"``).
"""

from typing import Any

__all__ = ["ServerSettings", "build_server"]

__version__ = "0.1.0"


def __getattr__(name: str) -> Any:
    if name == "build_server":
        from .server import build_server

        return build_server
    if name == "ServerSettings":
        from .settings import ServerSettings

        return ServerSettings
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
