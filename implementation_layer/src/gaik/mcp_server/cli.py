"""Command line of the MCP server: ``gaik-mcp`` and ``python -m gaik.mcp_server``.

Only the standard library is imported here at module level. The console script is installed
with every gaik install, so a missing MCP SDK is reported in one line, not as a traceback.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence

NEEDS_SDK = 'gaik-mcp needs the MCP SDK: pip install "gaik[mcp]"'
NEEDS_TOKEN = (
    "gaik-mcp: the HTTP transport needs a bearer token. Set GAIK_MCP_TOKEN "
    "(in the environment or in the --env-file file)."
)
SHORT_TOKEN = (
    "gaik-mcp: GAIK_MCP_TOKEN must be at least {least} characters. Make one with: "
    'python -c "import secrets; print(secrets.token_urlsafe(32))"'
)
# Their messages name local paths and can quote a provider's error body.
QUIET_LOGGERS = ("gaik.software_components",)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gaik-mcp",
        description="GAIK toolkit operations as MCP tools, over stdio or Streamable HTTP.",
        epilog="Environment: GAIK_MCP_ROOT, GAIK_MCP_MAX_FILE_MB, GAIK_MCP_MAX_TEXT_CHARS, "
        "GAIK_MCP_TIMEOUT, GAIK_MCP_TOKEN (http), GAIK_MCP_ALLOWED_HOSTS (http), "
        "GAIK_DECIDE_URL and GAIK_DECIDE_API_KEY (Jev backend), and gaik's provider variables.",
    )
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument(
        "--root",
        metavar="DIR",
        help="the only folder path arguments may point into, and the one fields_to_word "
        "writes to (default: none, paths are refused). Not a whole drive or the home folder",
    )
    parser.add_argument(
        "--env-file",
        metavar="FILE",
        help="dotenv file loaded before the environment is read; set variables win",
    )
    parser.add_argument("--host", default="127.0.0.1", help="http: address to listen on")
    parser.add_argument("--port", type=int, default=8000, help="http: port to listen on")
    parser.add_argument(
        "--allowed-host",
        action="append",
        default=[],
        metavar="HOST",
        help="http: a Host header to accept besides localhost and 127.0.0.1; repeatable",
    )
    parser.add_argument("--provider", metavar="NAME", help="gaik provider, as in LLM_PROVIDER")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the server. Returns 0 when it stopped, 1 without the MCP SDK, 2 for bad settings."""
    args = _parser().parse_args(argv)
    if args.env_file:
        if not os.path.isfile(args.env_file):
            print("gaik-mcp: the --env-file file does not exist", file=sys.stderr)
            return 2
        from dotenv import load_dotenv

        load_dotenv(args.env_file)
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.CRITICAL)
    try:
        import mcp  # noqa: F401
    except ImportError:
        print(NEEDS_SDK, file=sys.stderr)
        return 1

    from .server import build_server, serve_http
    from .settings import MIN_TOKEN_CHARS, ServerSettings

    try:
        settings = ServerSettings.from_env(
            os.environ,
            root=args.root,
            provider=args.provider,
            allowed_hosts=args.allowed_host,
        )
    except ValueError as error:
        print(f"gaik-mcp: {error}", file=sys.stderr)
        return 2
    if args.transport == "http" and not settings.token:
        print(NEEDS_TOKEN, file=sys.stderr)
        return 2
    if args.transport == "http" and len(settings.token or "") < MIN_TOKEN_CHARS:
        print(SHORT_TOKEN.format(least=MIN_TOKEN_CHARS), file=sys.stderr)
        return 2

    server = build_server(settings)
    try:
        if args.transport == "http":
            serve_http(server, settings, host=args.host, port=args.port)
        else:
            server.run(transport="stdio")
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
