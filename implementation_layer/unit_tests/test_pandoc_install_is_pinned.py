"""install_pandoc.py installs one pinned Pandoc release, and only a file whose SHA-256
matches the pinned value."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import sys
import types
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "no-code-assets"
    / "agent-skills"
    / "skills"
    / "generate-structured-reports"
    / "scripts"
    / "install_pandoc.py"
)


@pytest.fixture
def ip():
    spec = importlib.util.spec_from_file_location("install_pandoc_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _serve(monkeypatch, ip, payload: bytes, seen: list[str]):
    def urlopen(url, timeout):
        seen.append(url)
        return _Response(payload)

    monkeypatch.setattr(ip.urllib.request, "urlopen", urlopen)


def test_every_platform_pins_an_installer_of_the_pinned_release(ip):
    assert ip.PANDOC_INSTALLERS
    for (system, _machine), (name, sha256, size) in ip.PANDOC_INSTALLERS.items():
        assert system in {"win32", "darwin", "linux"}
        assert ip.PANDOC_VERSION in name and name.endswith((".msi", ".pkg", ".deb"))
        assert len(sha256) == 64 and int(sha256, 16) >= 0 and size > 1_000_000


def test_a_matching_download_is_kept(ip, tmp_path, monkeypatch):
    payload = b"pandoc installer bytes"
    seen: list[str] = []
    _serve(monkeypatch, ip, payload, seen)
    path = ip.fetch_checked(
        "pandoc.pkg", hashlib.sha256(payload).hexdigest(), len(payload), tmp_path
    )
    assert path.read_bytes() == payload
    assert seen == [ip._RELEASE + "pandoc.pkg"]
    assert seen[0].startswith("https://github.com/jgm/pandoc/releases/download/")


@pytest.mark.parametrize("payload", [b"something else", b"pandoc installer bytes!!"])
def test_a_download_that_does_not_match_the_pin_is_deleted(ip, tmp_path, monkeypatch, payload):
    expected = b"pandoc installer bytes"
    _serve(monkeypatch, ip, payload, [])
    with pytest.raises(ip.InstallerMismatchError):
        ip.fetch_checked(
            "pandoc.pkg", hashlib.sha256(expected).hexdigest(), len(expected), tmp_path
        )
    assert not (tmp_path / "pandoc.pkg").exists()


def test_the_install_unpacks_only_the_checked_file(ip, monkeypatch):
    checked: list[Path] = []
    unpacked: list[dict] = []

    def fetch(name, sha256, size, folder):
        path = folder / name
        path.write_bytes(b"ok")
        checked.append(path)
        return path

    def unpack(**kwargs):
        assert (Path(kwargs["download_folder"]) / kwargs["url"].rsplit("/", 1)[1]).exists()
        unpacked.append(kwargs)

    fake = types.ModuleType("pypandoc.pandoc_download")
    fake.download_pandoc = unpack
    monkeypatch.setitem(sys.modules, "pypandoc", types.ModuleType("pypandoc"))
    monkeypatch.setitem(sys.modules, "pypandoc.pandoc_download", fake)
    monkeypatch.setattr(ip, "fetch_checked", fetch)
    monkeypatch.setattr(ip, "pinned_installer", lambda: ("pandoc-x.pkg", "0" * 64, 2))
    ip.download_pandoc()
    assert len(checked) == 1 and len(unpacked) == 1
    assert unpacked[0]["url"] == ip._RELEASE + "pandoc-x.pkg"


def test_a_mismatch_is_reported_as_a_failed_install(ip, capsys, monkeypatch):
    monkeypatch.setattr(
        ip, "find_pandoc", lambda: {"found": False, "reason": "the Pandoc program is not installed"}
    )

    def mismatch():
        raise ip.InstallerMismatchError("the downloaded x does not match the pinned SHA-256")

    monkeypatch.setattr(ip, "download_pandoc", mismatch)
    code, result = ip.run(check_only=False)
    assert code == ip.EXIT_MISSING and "does not match the pinned SHA-256" in result["reason"]
