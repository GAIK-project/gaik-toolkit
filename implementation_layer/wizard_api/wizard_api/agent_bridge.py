"""Runs the wizard's agent CLI in its own container, next to the api.

The Claude Agent SDK starts the CLI as a subprocess and talks to it over stdin
and stdout; the tool hook, the wizard's own tools and the control protocol all
travel on those pipes. When ``WIZARD_AGENT_BRIDGE_SOCKET`` is set, the SDK is
given ``wizard-agent-cli`` as its CLI instead. That small client passes its
arguments, working directory and a short list of variables over a Unix socket
to ``wizard-agent-bridge`` in the agent container, which starts the real CLI
there and relays its pipes back. The agent and every command it runs then live
in a container that has the model settings and the sessions volume, and not the
api's database address, service token or cluster credentials.

    wizard-agent-bridge [--socket PATH]      # the agent container's command
    wizard-agent-cli <CLI arguments>         # what the SDK runs in the api container

Frames on the socket after the request: one byte for the kind, four bytes of
length, the payload. From the client: ``i`` stdin bytes, ``e`` end of stdin,
``s`` a signal name. From the bridge: ``o`` stdout, ``r`` stderr, ``x`` the exit
code, ``f`` why the CLI could not be started.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import struct
import sys
from pathlib import Path

SOCKET_ENV = "WIZARD_AGENT_BRIDGE_SOCKET"
CLI_ENV = "WIZARD_AGENT_CLI"
ROOTS_ENV = "WIZARD_AGENT_ROOTS"
DEFAULT_SOCKET = "/run/wizard-agent/agent.sock"

#: Variables the api may hand to the CLI. Everything else the CLI sees comes from
#: the agent container's own environment.
PASSED_PREFIXES = ("CLAUDE_", "ANTHROPIC_")
PASSED_NAMES = frozenset(
    {"API_TIMEOUT_MS", "DISABLE_TELEMETRY", "MAX_THINKING_TOKENS", "TRACEPARENT", "TRACESTATE"}
)

_HEADER = struct.Struct("!cI")
_MAX_REQUEST = 1 << 20
_SIGNALS = {"TERM": signal.SIGTERM, "INT": signal.SIGINT, "KILL": signal.SIGKILL}


def passed_env(env: dict[str, str]) -> dict[str, str]:
    """The part of the api's environment the bridge lets through to the CLI."""
    return {
        key: value
        for key, value in env.items()
        if key.startswith(PASSED_PREFIXES) or key in PASSED_NAMES
    }


def cli_path() -> str:
    """The real agent CLI in this container: the one the SDK bundles, unless set."""
    explicit = os.getenv(CLI_ENV, "").strip()
    if explicit:
        return explicit
    try:
        import claude_agent_sdk

        bundled = Path(claude_agent_sdk.__file__).parent / "_bundled" / "claude"
        if bundled.is_file():
            return str(bundled)
    except ImportError:
        pass
    return shutil.which("claude") or "claude"


def allowed_roots() -> list[Path]:
    """Folders the CLI may be started in: the wizard and the sessions volume."""
    raw = os.getenv(ROOTS_ENV, "").strip()
    if raw:
        parts = raw.split(os.pathsep)
    else:
        parts = [
            os.getenv("WIZARD_DIR", "").strip() or "/solution_wizard",
            os.getenv("WIZARD_SESSION_OUTPUT_ROOT", ""),
        ]
    return [Path(p).resolve() for p in parts if p.strip()]


def _inside(path: Path, roots: list[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


async def _send(writer: asyncio.StreamWriter, kind: bytes, payload: bytes = b"") -> None:
    writer.write(_HEADER.pack(kind, len(payload)) + payload)
    await writer.drain()


async def _receive(reader: asyncio.StreamReader) -> tuple[bytes, bytes]:
    kind, size = _HEADER.unpack(await reader.readexactly(_HEADER.size))
    return kind, await reader.readexactly(size) if size else b""


# --------------------------------------------------------------------------- bridge


def _check_request(request: object) -> tuple[list[str], str, dict[str, str]]:
    if not isinstance(request, dict):
        raise ValueError("the request is not an object")
    argv = request.get("argv")
    if not isinstance(argv, list) or not all(isinstance(a, str) for a in argv):
        raise ValueError("argv must be a list of strings")
    cwd = request.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        raise ValueError("cwd is missing")
    folder = Path(cwd).resolve()
    if not _inside(folder, allowed_roots()):
        raise ValueError("the working folder is outside the wizard and the sessions volume")
    env = request.get("env") or {}
    if not isinstance(env, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in env.items()
    ):
        raise ValueError("env must map strings to strings")
    return argv, str(folder), {**os.environ, **passed_env(env), "PWD": str(folder)}


async def _relay_out(stream: asyncio.StreamReader, kind: bytes, writer, lock) -> None:
    while chunk := await stream.read(65536):
        async with lock:
            await _send(writer, kind, chunk)


async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    lock = asyncio.Lock()
    process = None
    try:
        size = struct.unpack("!I", await reader.readexactly(4))[0]
        if size > _MAX_REQUEST:
            raise ValueError("the request is too large")
        argv, cwd, env = _check_request(json.loads(await reader.readexactly(size)))
        process = await asyncio.create_subprocess_exec(
            cli_path(),
            *argv,
            cwd=cwd,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (ValueError, OSError, asyncio.IncompleteReadError, json.JSONDecodeError) as exc:
        await _send(writer, b"f", str(exc).encode())
        writer.close()
        return

    async def relay_in() -> None:
        try:
            while True:
                kind, payload = await _receive(reader)
                if kind == b"i" and process.stdin:
                    process.stdin.write(payload)
                    await process.stdin.drain()
                elif kind == b"e" and process.stdin:
                    process.stdin.close()
                elif kind == b"s" and payload.decode() in _SIGNALS:
                    process.send_signal(_SIGNALS[payload.decode()])
        except (asyncio.IncompleteReadError, ConnectionError, BrokenPipeError):
            # The client is gone (the api ended the agent, or died): so is the CLI.
            if process.returncode is None:
                process.kill()

    inbound = asyncio.create_task(relay_in())
    await asyncio.gather(
        _relay_out(process.stdout, b"o", writer, lock),
        _relay_out(process.stderr, b"r", writer, lock),
        return_exceptions=True,
    )
    code = await process.wait()
    inbound.cancel()
    try:
        async with lock:
            await _send(writer, b"x", str(code).encode())
        writer.close()
    except ConnectionError:
        pass


async def serve(socket_path: str) -> None:
    path = Path(socket_path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    # Owner only, from the moment it exists: the containers of one pod run as the
    # same user, so the api's client can connect and nobody else can.
    previous = os.umask(0o177)
    try:
        server = await asyncio.start_unix_server(_handle, path=str(path))
    finally:
        os.umask(previous)
    async with server:
        await server.serve_forever()


def server_main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    socket_path = os.getenv(SOCKET_ENV, DEFAULT_SOCKET)
    if args[:1] == ["--socket"] and len(args) > 1:
        socket_path = args[1]
    asyncio.run(serve(socket_path))


# --------------------------------------------------------------------------- client


async def _client(argv: list[str]) -> int:
    socket_path = os.getenv(SOCKET_ENV, DEFAULT_SOCKET)
    reader, writer = await asyncio.open_unix_connection(socket_path)
    request = json.dumps(
        {"argv": argv, "cwd": os.getcwd(), "env": passed_env(dict(os.environ))}
    ).encode()
    writer.write(struct.pack("!I", len(request)) + request)
    await writer.drain()

    loop = asyncio.get_running_loop()
    lock = asyncio.Lock()

    def forward(name: str) -> None:
        async def send() -> None:
            async with lock:
                await _send(writer, b"s", name.encode())

        loop.create_task(send())

    for name in ("TERM", "INT"):
        loop.add_signal_handler(_SIGNALS[name], forward, name)

    stdin = asyncio.StreamReader()
    try:
        await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(stdin), sys.stdin)
    except (ValueError, OSError):
        stdin.feed_eof()  # not a pipe (a version check, say): nothing to relay

    async def relay_stdin() -> None:
        while chunk := await stdin.read(65536):
            async with lock:
                await _send(writer, b"i", chunk)
        async with lock:
            await _send(writer, b"e")

    inbound = asyncio.create_task(relay_stdin())
    out, err = sys.stdout.buffer, sys.stderr.buffer
    try:
        while True:
            kind, payload = await _receive(reader)
            if kind == b"o":
                out.write(payload)
                out.flush()
            elif kind == b"r":
                err.write(payload)
                err.flush()
            elif kind == b"x":
                return int(payload or b"1")
            elif kind == b"f":
                err.write(b"agent bridge: " + payload + b"\n")
                err.flush()
                return 127
    except asyncio.IncompleteReadError:
        err.write(b"agent bridge: the connection to the agent container closed\n")
        return 1
    finally:
        inbound.cancel()
        writer.close()


def client_main(argv: list[str] | None = None) -> None:
    try:
        code = asyncio.run(_client(list(sys.argv[1:] if argv is None else argv)))
    except (FileNotFoundError, ConnectionRefusedError) as exc:
        sys.stderr.write(f"agent bridge: the agent container is not reachable ({exc})\n")
        code = 127
    sys.exit(code)


if __name__ == "__main__":
    if sys.argv[1:2] == ["serve"]:
        server_main(sys.argv[2:])
    else:
        client_main()
