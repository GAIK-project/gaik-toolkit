"""The agent CLI runs in its own container: the bridge relays its pipes and passes nothing else."""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
from wizard_api import agent_bridge

BIN = Path(sys.executable).parent

FAKE_CLI = """#!{python}
import json, os, sys, time
seen = {{
    "argv": sys.argv[1:],
    "cwd": os.getcwd(),
    "env": {{k: v for k, v in os.environ.items() if k.startswith(("CLAUDE_", "SAMPLE_", "API_"))}},
}}
if sys.argv[1:2] == ["--wait"]:
    open(sys.argv[2], "w").write(str(os.getpid()))
    time.sleep(60)
print(json.dumps(seen), flush=True)
for line in sys.stdin:
    print(line.strip().upper(), flush=True)
sys.stderr.write("to stderr\\n")
sys.exit(3)
"""


@pytest.fixture
def bridge():
    # Short: a Unix socket path must stay under about 100 characters.
    root = Path(tempfile.mkdtemp(prefix="wab", dir="/tmp"))
    work = root / "work"
    work.mkdir()
    cli = root / "cli"
    cli.write_text(FAKE_CLI.format(python=sys.executable))
    cli.chmod(0o755)
    socket = root / "a.sock"
    env = {
        **os.environ,
        agent_bridge.CLI_ENV: str(cli),
        agent_bridge.ROOTS_ENV: str(work),
        "SAMPLE_AGENT_SIDE": "from the agent container",
    }
    server = subprocess.Popen(
        [str(BIN / "wizard-agent-bridge"), "--socket", str(socket)],
        env=env,
        stderr=subprocess.PIPE,
    )
    for _ in range(100):
        if socket.exists():
            break
        time.sleep(0.05)
    assert socket.exists(), server.stderr.read() if server.poll() is not None else "no socket"
    yield {"root": root, "work": work, "socket": socket}
    server.terminate()
    server.wait(timeout=5)
    shutil.rmtree(root, ignore_errors=True)


def _client(bridge, args, *, cwd=None, extra_env=None, **kwargs):
    env = {
        "PATH": os.environ.get("PATH", ""),
        agent_bridge.SOCKET_ENV: str(bridge["socket"]),
        "CLAUDE_CONFIG_DIR": "/data/sessions/.claude-agent",
        "API_TIMEOUT_MS": "600000",
        "SAMPLE_API_SIDE": "from the api container",
        **(extra_env or {}),
    }
    return subprocess.Popen(
        [str(BIN / "wizard-agent-cli"), *args],
        cwd=cwd or bridge["work"],
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **kwargs,
    )


def test_the_cli_runs_in_the_agent_container_with_the_pipes_relayed(bridge) -> None:
    client = _client(bridge, ["--output-format", "stream-json"])
    out, err = client.communicate(b"first\nsecond\n", timeout=20)

    lines = out.decode().splitlines()
    seen = json.loads(lines[0])
    assert seen["argv"] == ["--output-format", "stream-json"]
    assert Path(seen["cwd"]).resolve() == bridge["work"].resolve()
    assert lines[1:] == ["FIRST", "SECOND"]
    assert b"to stderr" in err
    assert client.returncode == 3


def test_only_the_agents_own_settings_cross_from_the_api(bridge) -> None:
    client = _client(bridge, [])
    out, _ = client.communicate(b"", timeout=20)

    env = json.loads(out.decode().splitlines()[0])["env"]
    assert env["CLAUDE_CONFIG_DIR"] == "/data/sessions/.claude-agent"
    assert env["API_TIMEOUT_MS"] == "600000"
    assert "SAMPLE_API_SIDE" not in env
    assert env["SAMPLE_AGENT_SIDE"] == "from the agent container"


def test_only_the_owner_can_reach_the_socket(bridge) -> None:
    assert bridge["socket"].stat().st_mode & 0o777 == 0o600


def test_a_folder_outside_the_wizard_and_the_sessions_is_refused(bridge) -> None:
    client = _client(bridge, [], cwd=bridge["root"])
    _, err = client.communicate(b"", timeout=20)
    assert client.returncode == 127
    assert b"outside" in err


@pytest.mark.parametrize("how", ["term", "kill"])
def test_the_cli_ends_when_the_api_ends_the_client(bridge, how) -> None:
    pid_file = bridge["work"] / "pid"
    client = _client(bridge, ["--wait", str(pid_file)])
    for _ in range(100):
        if pid_file.exists() and pid_file.read_text():
            break
        time.sleep(0.05)
    pid = int(pid_file.read_text())

    client.send_signal(signal.SIGTERM if how == "term" else signal.SIGKILL)
    client.wait(timeout=10)

    for _ in range(100):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        pytest.fail("the CLI kept running")


def test_the_api_env_is_filtered_to_the_agents_settings() -> None:
    passed = agent_bridge.passed_env(
        {
            "ANTHROPIC_MODEL": "m",
            "CLAUDE_CODE_ENTRYPOINT": "sdk-py",
            "DISABLE_TELEMETRY": "1",
            "WIZARD_DATABASE_URL": "postgresql://x",
            "WIZARD_API_TOKEN": "t",
            "KUBERNETES_SERVICE_HOST": "10.0.0.1",
            "HOME": "/",
        }
    )
    assert passed == {
        "ANTHROPIC_MODEL": "m",
        "CLAUDE_CODE_ENTRYPOINT": "sdk-py",
        "DISABLE_TELEMETRY": "1",
    }


def test_the_sdk_starts_the_bridge_client_when_the_socket_is_set(monkeypatch, tmp_path) -> None:
    from wizard_api.services import agent_service
    from wizard_api.services.agent_tool_guard import ToolGuard

    if agent_service.ClaudeAgentOptions is None:
        pytest.skip("claude-agent-sdk is not installed")
    monkeypatch.setenv(agent_bridge.SOCKET_ENV, "/run/wizard-agent/agent.sock")
    guard = ToolGuard(tmp_path, tmp_path)
    options = agent_service._build_options(tmp_path, tmp_path, guard=guard)
    assert Path(options.cli_path).name == "wizard-agent-cli"

    monkeypatch.delenv(agent_bridge.SOCKET_ENV)
    assert agent_service._build_options(tmp_path, tmp_path, guard=guard).cli_path is None


def test_only_the_api_container_has_the_service_secrets_and_a_cluster_token() -> None:
    yaml = pytest.importorskip("yaml")
    manifest = Path(__file__).resolve().parents[2] / "deploy" / "openshift" / "deployment-api.yaml"
    pod = yaml.safe_load(manifest.read_text())["spec"]["template"]["spec"]
    assert pod["automountServiceAccountToken"] is False
    api, agent = pod["containers"]
    api_env = {e["name"] for e in api["env"]}
    agent_env = {e["name"] for e in agent["env"]}

    assert {"WIZARD_DATABASE_URL", "WIZARD_API_TOKEN", "WIZARD_AGENT_BRIDGE_SOCKET"} <= api_env
    assert not agent_env & {"WIZARD_DATABASE_URL", "WIZARD_API_TOKEN"}
    assert "ANTHROPIC_FOUNDRY_API_KEY" in agent_env
    mounts = {m["name"] for m in agent["volumeMounts"]}
    assert mounts == {"session-output", "agent-socket"}
    assert "cluster-token" in {m["name"] for m in api["volumeMounts"]}
    assert agent["command"][0] == "wizard-agent-bridge"
