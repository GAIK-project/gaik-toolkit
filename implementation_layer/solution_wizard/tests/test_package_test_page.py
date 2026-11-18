"""Every generated package carries a test page: app.py, ui/index.html and ui/solution.json.

The server and the page are fixed files; the blueprint reaches them only as data in
ui/solution.json. The server is started here on a free port against a stand-in
run_poc.py that makes no model call.
"""

import ast
import hashlib
import http.client
import importlib.util
import io
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import types
import zipfile
from pathlib import Path, PurePosixPath

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from solution_wizard.blueprint import Blueprint  # noqa: E402
from solution_wizard.scaffolder import _artifact_names, scaffold_poc  # noqa: E402
from test_hybrid_generic import _hybrid_blueprint  # noqa: E402

WIZARD_DIR = Path(__file__).parent.parent
EXAMPLES = WIZARD_DIR / "examples"
COMMON = WIZARD_DIR / "templates" / "poc" / "_common"
PAGE_FILES = ("app.py", "ui/index.html", "ui/solution.json")

HOSTILE = "</script><img src=x onerror=alert(1)> \"quoted\" & 'single' <b>bold</b>"

#: Stands in for the generated entrypoint: reads what the run was given, writes a
#: result and one file of each kind the server must and must not hand out.
FAKE_RUN_POC = """\
import hashlib, json, sys, time
from pathlib import Path

here = Path(__file__).parent
sample = here / "sample_input"
names = sorted(p.name for p in sample.iterdir() if p.is_file())
print("Reading", names)
if "slow.pdf" in names:
    time.sleep(3)
if "tree.pdf" in names:
    # A process of the entrypoint's own, as a parser or a worker pool starts one.
    import os, subprocess
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    Path(os.environ["POC_TEST_PIDFILE"]).write_text(str(child.pid), encoding="utf-8")
    time.sleep(60)
if "fail.pdf" in names:
    print("ERROR: No usable text in fail.pdf", file=sys.stderr)
    sys.exit(3)
uploaded = []
if ".uploaded" in names:
    uploaded = (sample / ".uploaded").read_text(encoding="utf-8").splitlines()
documents = [n for n in names if n.endswith(".pdf")]
question = ""
if "question.txt" in names:
    question = (sample / "question.txt").read_text(encoding="utf-8").strip()
out = here / "output"
out.mkdir(exist_ok=True)
stem = Path(documents[0]).stem if documents else "run"
result = {
    "po_number": "PO-1042",
    "supplier_name": "Northwind <b>Oy</b>",
    "line_items": [{"sku": "A-1", "quantity": 2}],
    "seen": names,
    "uploaded": uploaded,
    "question": question,
    "sha256": hashlib.sha256((sample / documents[0]).read_bytes()).hexdigest() if documents else "",
    "env_seen": (here / ".env").is_file(),
    "stdin_is_terminal": bool(sys.stdin and sys.stdin.isatty()),
    "cwd_is_package": (here / "ui").exists(),
}
(out / f"{stem}_result.json").write_text(json.dumps(result), encoding="utf-8")
(out / f"{stem}_validation.json").write_text("{}", encoding="utf-8")
(out / "notes.py").write_text("not an output kind", encoding="utf-8")
print("Wrote the result")
"""


def _scaffold(tmp_path: Path, blueprint: Blueprint | None = None) -> Path:
    bp = blueprint or Blueprint.from_file(EXAMPLES / "document_extraction_blueprint.json")
    return scaffold_poc(bp, tmp_path)["poc_dir"]


# ---------------------------------------------------------------------------
# What the scaffolder writes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("example", "pattern", "kind", "asks_question"),
    [
        ("document_extraction_blueprint.json", "document_to_structured", "document", False),
        ("incident_reporting_blueprint.json", "audio_to_structured", "audio", False),
        ("rag_workflow_blueprint.json", "rag", "document", True),
    ],
)
def test_every_wired_pattern_gets_the_test_page(tmp_path, example, pattern, kind, asks_question):
    result = scaffold_poc(Blueprint.from_file(EXAMPLES / example), tmp_path)
    poc = result["poc_dir"]

    assert result["pattern"] == pattern
    for name in PAGE_FILES:
        assert (poc / name).is_file(), name
        assert poc / name in result["files"], name
    described = json.loads((poc / "ui" / "solution.json").read_text(encoding="utf-8"))
    assert described["pattern"] == pattern
    assert described["inputs"][0]["kind"] == kind
    assert described["inputs"][0]["extensions"]
    assert described["asks_question"] is asks_question


def test_a_pipeline_the_agent_wires_gets_the_test_page_too(tmp_path):
    result = scaffold_poc(_hybrid_blueprint(), tmp_path)
    poc = result["poc_dir"]

    for name in PAGE_FILES:
        assert (poc / name).is_file(), name
    described = json.loads((poc / "ui" / "solution.json").read_text(encoding="utf-8"))
    # audio + pdf: one input of each kind, each with the endings its kind takes.
    assert {i["kind"] for i in described["inputs"]} == {"audio", "document"}
    assert all(i["multiple"] for i in described["inputs"])
    assert [f["key"] for f in described["output_fields"]] == ["field_alpha", "field_beta"]


def test_an_input_type_the_scaffolder_does_not_know_takes_any_file(tmp_path):
    bp = _hybrid_blueprint()
    bp.technical_spec["input_types"] = ["sensor_log"]
    described = json.loads(
        (_scaffold(tmp_path, bp) / "ui" / "solution.json").read_text(encoding="utf-8")
    )

    assert described["inputs"] == [
        {
            "kind": "file",
            "label": "The solution's input files",
            "extensions": [],
            "multiple": True,
        }
    ]


def test_a_finnish_solution_gets_finnish_labels(tmp_path):
    bp = Blueprint.from_file(EXAMPLES / "incident_reporting_blueprint.json")
    described = json.loads(
        (_scaffold(tmp_path, bp) / "ui" / "solution.json").read_text(encoding="utf-8")
    )

    assert described["language"] == "fi"
    assert described["inputs"][0]["label"] == "Äänite"


def test_the_output_fields_carry_their_type_and_description(tmp_path):
    bp = Blueprint.from_file(EXAMPLES / "document_extraction_blueprint.json")
    bp.target_output_spec["field_types"] = {"total_amount": "decimal"}
    bp.target_output_spec["field_descriptions"] = {"total_amount": "The order's total with tax."}
    described = json.loads(
        (_scaffold(tmp_path, bp) / "ui" / "solution.json").read_text(encoding="utf-8")
    )

    fields = {f["key"]: f for f in described["output_fields"]}
    assert list(fields) == bp.target_output_spec["fields"]
    assert fields["total_amount"] == {
        "key": "total_amount",
        "label": "Total amount",
        "type": "decimal",
        "description": "The order's total with tax.",
    }
    assert fields["po_number"] == {"key": "po_number", "label": "Po number", "type": "string"}


def test_the_server_and_the_page_are_the_same_in_every_package(tmp_path):
    """No blueprint value is written into the code or the markup."""
    bp = Blueprint.from_file(EXAMPLES / "document_extraction_blueprint.json")
    bp.use_case.name = HOSTILE
    bp.use_case.description = HOSTILE
    poc = _scaffold(tmp_path, bp)

    app = (poc / "app.py").read_text(encoding="utf-8")
    page = (poc / "ui" / "index.html").read_text(encoding="utf-8")
    assert app == (COMMON / "app.py.tmpl").read_text(encoding="utf-8")
    assert page == (COMMON / "ui" / "index.html").read_text(encoding="utf-8")
    assert "onerror" not in app + page
    ast.parse(app)


def test_hostile_blueprint_text_is_inert_data_in_solution_json(tmp_path):
    bp = Blueprint.from_file(EXAMPLES / "document_extraction_blueprint.json")
    bp.use_case.name = HOSTILE
    bp.use_case.description = HOSTILE + "\nsecond line\u2028third"
    bp.target_output_spec["field_descriptions"] = {"po_number": HOSTILE}
    poc = _scaffold(tmp_path, bp)

    raw = (poc / "ui" / "solution.json").read_text(encoding="utf-8")
    # Nothing in the file can end a tag or a script, wherever a page puts it.
    assert not any(char in raw for char in "<>&\u2028\u2029")
    described = json.loads(raw)
    # And read back it is the text as written, on one line.
    assert described["name"] == HOSTILE
    assert described["purpose"] == HOSTILE + " second line third"
    assert described["output_fields"][0]["description"] == HOSTILE


def test_the_page_puts_text_on_screen_as_text_and_loads_nothing_from_elsewhere():
    page = (COMMON / "ui" / "index.html").read_text(encoding="utf-8")

    for markup_sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert markup_sink not in page, markup_sink
    assert "textContent" in page
    for elsewhere in ("http://", "https://", 'src="//', "@import", "<link"):
        assert elsewhere not in page, elsewhere
    assert '<meta name="viewport"' in page


def test_the_server_needs_the_standard_library_only():
    tree = ast.parse((COMMON / "app.py.tmpl").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported - {"__future__"} <= sys.stdlib_module_names
    # Gone from Python 3.13.
    assert "cgi" not in imported


def test_the_readme_says_how_to_start_the_page_and_names_its_addresses(tmp_path):
    readme = (_scaffold(tmp_path) / "README.md").read_text(encoding="utf-8")

    assert "python app.py" in readme
    assert "http://127.0.0.1:8000" in readme
    assert "GET /api/solution" in readme
    assert "POST /api/run" in readme


# ---------------------------------------------------------------------------
# The server
# ---------------------------------------------------------------------------


class Page:
    """A generated package with a stand-in entrypoint, and its server on a free port."""

    def __init__(self, poc: Path, host: str = "127.0.0.1", **limits):
        self.poc = poc
        (poc / "run_poc.py").write_text(FAKE_RUN_POC, encoding="utf-8")
        spec = importlib.util.spec_from_file_location(f"poc_app_{id(self)}", poc / "app.py")
        self.app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.app)
        self.server = self.app.create_server(poc, host, 0, **limits)
        self.address, self.port = self.server.server_address[:2]
        if host in ("0.0.0.0", "::"):
            # Listening on every address: this computer reaches it on its loopback.
            self.address = "127.0.0.1"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.server.solution.close()

    def request(self, method, path, body=None, headers=None):
        return _request(self.address, self.port, method, path, body, headers)

    def get_json(self, path):
        status, _, body = self.request("GET", path)
        return status, json.loads(body)

    def run(self, files=(), headers=None, **fields):
        return _post_run(self.address, self.port, files, headers, **fields)


def _request(address, port, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection(address, port, timeout=60)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def _post_run(address, port, files=(), headers=None, **fields):
    """POST /api/run with ``files`` (name, bytes) and text ``fields``, as the page sends them."""
    boundary = "----test-boundary-7d1"
    parts = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
            + value.encode("utf-8")
            + b"\r\n"
        )
    for filename, content in files:
        parts.append(
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="files"; '
                f'filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'
            ).encode()
            + content
            + b"\r\n"
        )
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    status, _, answer = _request(
        address,
        port,
        "POST",
        "/api/run",
        body=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            **(headers or {}),
        },
    )
    return status, json.loads(answer)


@pytest.fixture
def page(tmp_path):
    served = Page(_scaffold(tmp_path))
    yield served
    served.close()


def _page_with(tmp_path, **limits) -> Page:
    return Page(_scaffold(tmp_path), **limits)


def test_the_page_and_the_description_are_served(page):
    status, headers, body = page.request("GET", "/")
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert "default-src 'none'" in headers["Content-Security-Policy"]
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert body == (page.poc / "ui" / "index.html").read_bytes()

    status, described = page.get_json("/api/solution")
    assert status == 200
    assert described["name"] == "Purchase Order Data Extraction"
    assert described["limits"]["max_upload_bytes"] == 50 * 1024 * 1024
    assert described["env_file"] is False
    assert described["sample_files"] == []


def test_a_run_returns_the_result_and_its_file_can_be_downloaded(page):
    # Bytes that look like line ends and like a boundary must arrive as they were sent.
    document = b"%PDF-1.4\r\n--\r\n----test\n\r\x00\xff\xfe" + bytes(range(256)) * 4
    (page.poc / "output" / "earlier.json").write_text("{}", encoding="utf-8")

    status, answer = page.run(files=[("order 1042.pdf", document)])

    assert status == 200
    assert answer["ok"] is True
    assert answer["exit_code"] == 0
    assert answer["used_examples"] is False
    assert "Wrote the result" in answer["log_tail"]
    result = answer["result"]
    assert result["po_number"] == "PO-1042"
    assert result["sha256"] == hashlib.sha256(document).hexdigest()
    assert result["seen"] == [".uploaded", "order 1042.pdf"]
    assert result["uploaded"] == ["order 1042.pdf"]
    # The run had no terminal, and it ran in a folder of its own.
    assert result["stdin_is_terminal"] is False
    assert result["cwd_is_package"] is False

    outputs = {o["name"]: o for o in answer["outputs"]}
    # The validation report is listed but is not the result; notes.py is no output kind.
    assert set(outputs) == {"order 1042_result.json", "order 1042_validation.json"}
    main = outputs["order 1042_result.json"]
    assert main["kind"] == "json"
    status, headers, body = page.request("GET", main["url"])
    assert status == 200
    assert headers["Content-Disposition"].startswith("attachment")
    assert json.loads(body) == result
    assert len(body) == main["size"]

    # The package's own folders are as they were.
    assert list((page.poc / "sample_input").iterdir()) == []
    assert [p.name for p in (page.poc / "output").iterdir()] == ["earlier.json"]


def test_a_question_becomes_the_text_file_the_rag_entrypoint_reads(tmp_path):
    bp = Blueprint.from_file(EXAMPLES / "rag_workflow_blueprint.json")
    served = Page(_scaffold(tmp_path, bp))
    try:
        (served.poc / "sample_input" / "handbook.pdf").write_bytes(b"%PDF-1.4 handbook")
        (served.poc / "sample_input" / "sample_questions.txt").write_text("Old?\n", "utf-8")

        status, answer = served.run(question="  Kuka hyväksyy lomat?  ")

        assert status == 200, answer
        result = answer["result"]
        # No file was sent, so the package's example documents are the material.
        # The examples' own question file is left out: the run answers what was
        # asked, not the sample questions as well.
        assert answer["used_examples"] is True
        assert result["seen"] == [".uploaded", "handbook.pdf", "question.txt"]
        assert result["uploaded"] == ["question.txt"]
        assert result["question"] == "Kuka hyväksyy lomat?"
        assert served.get_json("/api/solution")[1]["sample_files"] == [
            "handbook.pdf",
            "sample_questions.txt",
        ]
    finally:
        served.close()


def test_the_question_file_the_page_writes_is_one_the_rag_template_reads(tmp_path):
    """The names in app.py and in rag/run_poc.py.tmpl must stay the same."""
    rag = (WIZARD_DIR / "templates" / "poc" / "rag" / "run_poc.py.tmpl").read_text("utf-8")
    bundle = (COMMON / "input_bundle.py.tmpl").read_text("utf-8")
    app = (COMMON / "app.py.tmpl").read_text("utf-8")

    assert 'QUESTION_SUFFIXES = (".txt", ".md")' in rag
    assert '("question", "question.txt")' in app
    assert 'UPLOADED_NAMES_FILE = ".uploaded"' in bundle
    assert 'UPLOADED_NAMES_FILE = ".uploaded"' in app


def _text_only_blueprint() -> Blueprint:
    bp = _hybrid_blueprint()
    bp.technical_spec["input_types"] = ["text"]
    return bp


def test_a_text_only_solution_takes_a_text_file_as_well_as_typed_text(tmp_path):
    """Typed text is capped, and the refusal says to send a file: the file must be takeable."""
    served = Page(_scaffold(tmp_path, _text_only_blueprint()))
    try:
        described = served.get_json("/api/solution")[1]
        assert [(i["kind"], i["extensions"]) for i in described["inputs"]] == [
            ("text", [".txt", ".md"])
        ]

        status, answer = served.run(files=[("notes.md", b"# Long notes")])
        assert status == 200, answer
        assert answer["result"]["seen"] == [".uploaded", "notes.md"]

        status, answer = served.run(text="A short message")
        assert status == 200, answer
        assert answer["result"]["seen"] == [".uploaded", "input.txt"]

        status, answer = served.run(text="x" * 20_001)
        assert status == 413
        assert answer["error"] == {
            "code": "text_too_long",
            "message": "The text is too long. Send it as a file instead.",
        }
    finally:
        served.close()


def test_the_page_offers_the_file_drop_for_a_text_input_too():
    """The drop area was hidden when the only input was text (review, 17 Nov 2026)."""
    page = (COMMON / "ui" / "index.html").read_text(encoding="utf-8")

    # Nothing in the page hides the drop area or leaves the text input out of it.
    assert 'show($("drop")' not in page
    assert 'kind !== "text"' not in page
    assert 'id="drop" class="drop">' in page


def test_a_request_with_nothing_to_run_on_is_refused(page):
    status, answer = page.run()

    assert status == 400
    assert answer == {
        "ok": False,
        "error": {"code": "no_input", "message": "Add a file or a text first."},
    }


def test_a_file_the_solution_does_not_take_is_refused(page):
    status, answer = page.run(files=[("macro.exe", b"MZ")])

    assert status == 400
    assert answer["error"]["code"] == "bad_extension"
    assert page.get_json("/api/status")[1]["busy"] is False


def test_a_file_name_cannot_leave_the_input_folder(page):
    status, answer = page.run(files=[("../../evil.pdf", b"%PDF"), ("C:\\\\x\\\\also.pdf", b"%PDF")])

    assert status == 200
    assert answer["result"]["seen"] == [".uploaded", "also.pdf", "evil.pdf"]
    # Uploads go under the runs' own folder, so that is where a name that climbed
    # out of sample_input/ would have landed.
    root = page.server.solution.runs_root
    written = sorted(p.relative_to(root).as_posix() for p in root.rglob("*.pdf"))
    run_id = answer["run_id"]
    assert written == [f"{run_id}/sample_input/also.pdf", f"{run_id}/sample_input/evil.pdf"]
    assert not (root.parent / "evil.pdf").exists()
    assert not (page.poc.parent / "evil.pdf").exists()


def test_a_finnish_file_name_arrives_as_written(page):
    status, answer = page.run(files=[("tilaus ääkköset (1).pdf", b"%PDF")])

    assert status == 200
    assert answer["result"]["uploaded"] == ["tilaus ääkköset (1).pdf"]
    name = "tilaus ääkköset (1)_result.json"
    assert [o["name"] for o in answer["outputs"]][0] == name
    assert page.request("GET", answer["outputs"][0]["url"])[0] == 200


def test_two_files_of_one_name_are_both_kept(page):
    status, answer = page.run(files=[("a.pdf", b"one"), ("A.pdf", b"two")])

    assert status == 200
    assert answer["result"]["seen"] == [".uploaded", "A-1.pdf", "a.pdf"]


def test_more_bytes_than_the_cap_are_refused(tmp_path):
    served = _page_with(tmp_path, max_upload_bytes=1000)
    try:
        status, answer = served.run(files=[("big.pdf", b"x" * 200_000)])
        assert status == 413
        assert answer["error"]["code"] == "too_large"
        # Under the cap the same server still runs.
        status, answer = served.run(files=[("small.pdf", b"x" * 100)])
        assert status == 200 and answer["ok"] is True
    finally:
        served.close()


def test_more_files_than_the_cap_are_refused(tmp_path):
    served = _page_with(tmp_path, max_files=2)
    try:
        status, answer = served.run(files=[(f"{n}.pdf", b"x") for n in range(3)])
        assert status == 413
        assert answer["error"]["code"] == "too_many_files"
    finally:
        served.close()


def test_a_request_without_a_length_or_a_form_is_refused(page):
    status, _, body = page.request(
        "POST", "/api/run", body=b"{}", headers={"Content-Type": "application/json"}
    )
    assert status == 415
    assert json.loads(body)["error"]["code"] == "not_a_form"


@pytest.mark.parametrize(
    "name",
    [
        "../run_poc.py",
        "../config.yaml",
        "%2e%2e/config.yaml",
        "..%2Fconfig.yaml",
        "..%5Cconfig.yaml",
        "/etc/passwd",
        "%2Fetc%2Fpasswd",
        "notes.py",
        "missing.json",
        "",
    ],
)
def test_the_files_route_serves_output_files_only(page, name):
    status, answer = page.run(files=[("order.pdf", b"%PDF")])
    assert status == 200
    run_id = answer["run_id"]
    assert page.request("GET", f"/api/runs/{run_id}/files/order_result.json")[0] == 200

    status, _, body = page.request("GET", f"/api/runs/{run_id}/files/{name}")

    assert status == 404
    assert json.loads(body)["error"]["code"] == "not_found"


def test_an_unknown_run_has_no_files(page):
    for run_id in ("0" * 16, "..", "nope"):
        assert page.request("GET", f"/api/runs/{run_id}/files/order_result.json")[0] == 404


def test_a_second_run_is_refused_while_one_is_going(page):
    first = {}

    def slow():
        first["answer"] = page.run(files=[("slow.pdf", b"%PDF")])

    thread = threading.Thread(target=slow)
    thread.start()
    deadline = time.monotonic() + 20
    while not page.get_json("/api/status")[1]["busy"]:
        assert time.monotonic() < deadline, "the first run never started"
        time.sleep(0.05)

    status, answer = page.run(files=[("order.pdf", b"%PDF")])
    thread.join(timeout=60)

    assert status == 409
    assert answer["error"]["code"] == "busy"
    assert first["answer"][0] == 200 and first["answer"][1]["ok"] is True
    assert page.get_json("/api/status")[1] == {"busy": False, "elapsed_seconds": 0, "log_tail": ""}


def test_a_failed_run_says_so_in_plain_words_with_the_log(page):
    status, answer = page.run(files=[("fail.pdf", b"%PDF")])

    assert status == 200
    assert answer["ok"] is False
    assert answer["exit_code"] == 3
    assert answer["error"] == {
        "code": "run_failed",
        "message": "The run ended with an error. The log says why.",
    }
    assert "ERROR: No usable text in fail.pdf" in answer["log_tail"]
    assert answer["result"] is None


def test_a_run_that_takes_too_long_is_stopped(tmp_path):
    served = _page_with(tmp_path, timeout=0.5)
    try:
        status, answer = served.run(files=[("slow.pdf", b"%PDF")])
        assert status == 200
        assert answer["ok"] is False
        assert answer["error"]["code"] == "timeout"
    finally:
        served.close()


def test_a_server_error_answers_without_a_traceback(page, capsys):
    (page.poc / "run_poc.py").unlink()
    status, answer = page.run(files=[("order.pdf", b"%PDF")])
    assert status == 500
    assert answer["error"]["code"] == "no_entrypoint"

    # And an error nobody foresaw: the answer names no file, line or exception.
    page.server.solution.run = lambda fields, files: 1 / 0
    status, _, body = page.request(
        "POST",
        "/api/run",
        body=b"--b--\r\n",
        headers={"Content-Type": "multipart/form-data; boundary=b"},
    )
    assert status == 500
    text = body.decode("utf-8")
    assert json.loads(text)["error"]["code"] == "server_error"
    assert "Traceback" not in text and "ZeroDivisionError" not in text and ".py" not in text


def test_only_the_last_runs_are_kept(tmp_path):
    served = _page_with(tmp_path, keep_runs=1)
    try:
        first = served.run(files=[("one.pdf", b"%PDF")])[1]
        second = served.run(files=[("two.pdf", b"%PDF")])[1]

        assert served.request("GET", first["outputs"][0]["url"])[0] == 404
        assert served.request("GET", second["outputs"][0]["url"])[0] == 200
        kept = [p.name for p in served.server.solution.runs_root.iterdir() if p.is_dir()]
        assert kept == [second["run_id"]]
    finally:
        served.close()


def test_the_keys_file_is_there_for_the_run_and_gone_after_it(page):
    (page.poc / ".env").write_text("EXAMPLE_SETTING=1\n", encoding="utf-8")

    status, answer = page.run(files=[("order.pdf", b"%PDF")])

    assert status == 200
    assert answer["result"]["env_seen"] is True
    run_dir = page.server.solution.runs_root / answer["run_id"]
    assert (run_dir / "run_poc.py").is_file()
    assert not (run_dir / ".env").exists()
    assert page.get_json("/api/solution")[1]["env_file"] is True


def test_a_page_on_another_site_cannot_reach_the_server(page):
    status, _, body = page.request("GET", "/api/solution", headers={"Host": "attacker.example"})
    assert status == 403

    status, answer = page.run(
        files=[("order.pdf", b"%PDF")], headers={"Origin": "https://attacker.example"}
    )
    assert status == 403
    assert answer["error"]["code"] == "forbidden"

    own = {"Origin": f"http://127.0.0.1:{page.port}"}
    assert page.run(files=[("order.pdf", b"%PDF")], headers=own)[0] == 200


def test_the_working_folders_are_removed_when_the_server_closes(tmp_path):
    served = _page_with(tmp_path)
    served.run(files=[("order.pdf", b"%PDF")])
    root = served.server.solution.runs_root
    assert root.is_dir()

    served.close()

    assert not root.exists()


# ---------------------------------------------------------------------------
# Review of the pull request (17 Nov 2026)
# ---------------------------------------------------------------------------


def _rag_page(tmp_path) -> Page:
    return Page(_scaffold(tmp_path, Blueprint.from_file(EXAMPLES / "rag_workflow_blueprint.json")))


def test_only_the_rag_pattern_asks_a_question(tmp_path):
    """Only the RAG entrypoint reads a question file; "answer" as an output type is not enough."""
    bp = _hybrid_blueprint()
    bp.technical_spec["output_types"] = ["answer"]
    described = json.loads(
        (_scaffold(tmp_path / "a", bp) / "ui" / "solution.json").read_text(encoding="utf-8")
    )
    assert described["pattern"] != "rag"
    assert described["asks_question"] is False
    assert described["question_label"] == ""
    assert "text" not in {i["kind"] for i in described["inputs"]}

    # Typed text is offered where the blueprint says the solution takes text.
    bp = _hybrid_blueprint()
    bp.technical_spec["output_types"] = ["answer"]
    bp.technical_spec["input_types"] = ["text", "pdf"]
    described = json.loads(
        (_scaffold(tmp_path / "b", bp) / "ui" / "solution.json").read_text(encoding="utf-8")
    )
    assert described["asks_question"] is False
    assert {i["kind"] for i in described["inputs"]} == {"text", "document"}


def test_a_question_without_any_document_is_refused_before_a_run(tmp_path):
    """A deployable package has no sample_input/: a question alone has nothing to search."""
    served = _rag_page(tmp_path)
    try:
        refusal = {
            "ok": False,
            "error": {
                "code": "no_documents",
                "message": (
                    "Add at least one document: the question is asked of the documents you add."
                ),
            },
        }
        assert served.run(question="Who approves leave?") == (400, refusal)

        # Example question files are not documents either.
        (served.poc / "sample_input" / "sample_questions.txt").write_text("Old?", "utf-8")
        assert served.run(question="Who approves leave?") == (400, refusal)
        assert list(served.server.solution.runs_root.iterdir()) == []

        # With a document sent, or one among the examples, the question runs.
        status, answer = served.run(files=[("handbook.pdf", b"%PDF")], question="Who approves?")
        assert status == 200 and answer["ok"] is True
        (served.poc / "sample_input" / "policy.pdf").write_bytes(b"%PDF")
        status, answer = served.run(question="Who approves?")
        assert status == 200 and answer["result"]["seen"] == [
            ".uploaded",
            "policy.pdf",
            "question.txt",
        ]
    finally:
        served.close()


def test_a_run_without_a_question_keeps_the_examples_question_file(tmp_path):
    served = _rag_page(tmp_path)
    try:
        (served.poc / "sample_input" / "handbook.pdf").write_bytes(b"%PDF")
        (served.poc / "sample_input" / "sample_questions.txt").write_text("Old?", "utf-8")

        status, answer = served.run()

        assert status == 200
        assert answer["result"]["seen"] == ["handbook.pdf", "sample_questions.txt"]
    finally:
        served.close()


@pytest.mark.parametrize(
    ("name", "safe"),
    [
        ("CON", "_CON"),
        ("con.pdf", "_con.pdf"),
        ("NUL.txt", "_NUL.txt"),
        ("Aux.tar.gz", "_Aux.tar.gz"),
        ("prn", "_prn"),
        ("com1.pdf", "_com1.pdf"),
        ("LPT9", "_LPT9"),
        ("../nul.pdf", "_nul.pdf"),
        # Not device names.
        ("console.pdf", "console.pdf"),
        ("com10.pdf", "com10.pdf"),
        ("com0.pdf", "com0.pdf"),
        ("null.pdf", "null.pdf"),
    ],
)
def test_a_windows_device_name_is_renamed(page, name, safe):
    assert page.app.safe_name(name) == safe


def test_a_file_with_a_device_name_is_written_under_another_name(page):
    status, answer = page.run(files=[("NUL.pdf", b"%PDF")])

    assert status == 200
    assert answer["result"]["seen"] == [".uploaded", "_NUL.pdf"]


def _is_running(pid: int) -> bool:
    if os.name == "nt":
        listed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        return f'"{pid}"' in listed
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def test_a_timeout_stops_what_the_entrypoint_started_too(tmp_path, monkeypatch):
    pid_file = tmp_path / "child.pid"
    monkeypatch.setenv("POC_TEST_PIDFILE", str(pid_file))
    served = _page_with(tmp_path, timeout=4)
    try:
        status, answer = served.run(files=[("tree.pdf", b"%PDF")])

        assert status == 200
        assert answer["error"]["code"] == "timeout"
        child = int(pid_file.read_text(encoding="utf-8"))
        deadline = time.monotonic() + 10
        while _is_running(child) and time.monotonic() < deadline:
            time.sleep(0.2)
        assert not _is_running(child), "the entrypoint's own process outlived the run"
    finally:
        served.close()


def test_closing_the_server_stops_a_run_that_is_going(tmp_path, monkeypatch):
    pid_file = tmp_path / "child.pid"
    monkeypatch.setenv("POC_TEST_PIDFILE", str(pid_file))
    served = _page_with(tmp_path)
    thread = threading.Thread(target=lambda: served.run(files=[("tree.pdf", b"%PDF")]))
    thread.start()
    deadline = time.monotonic() + 30
    while not pid_file.exists() or not pid_file.read_text(encoding="utf-8"):
        assert time.monotonic() < deadline, "the run never started its own process"
        time.sleep(0.1)
    child = int(pid_file.read_text(encoding="utf-8"))

    served.server.solution.close()
    thread.join(timeout=30)
    served.close()

    deadline = time.monotonic() + 10
    while _is_running(child) and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not thread.is_alive()
    assert not _is_running(child)


@pytest.mark.parametrize("step", ["_copy_package", "_execute", "inputs"])
def test_a_run_that_cannot_be_prepared_leaves_no_folder_and_no_keys(page, step):
    """The keys file is among the first files copied; a failure after it removes it all."""
    (page.poc / ".env").write_text("EXAMPLE_SETTING=1", encoding="utf-8")
    solution = page.server.solution
    copied = {}

    if step == "_copy_package":
        copy_package = solution._copy_package

        def fail(run_dir):
            copy_package(run_dir)
            copied["env"] = (run_dir / ".env").is_file()
            raise OSError("disk full")

        solution._copy_package = fail
    elif step == "_execute":

        def fail(run_dir, log_path):
            copied["env"] = (run_dir / ".env").is_file()
            log_path.write_text("started", encoding="utf-8")
            raise OSError("cannot start")

        solution._execute = fail
    else:
        # The inputs cannot be written: their folder cannot be made.
        copy_package = solution._copy_package

        def blocked(run_dir):
            copy_package(run_dir)
            copied["env"] = (run_dir / ".env").is_file()
            (run_dir / "sample_input").mkdir()

        solution._copy_package = blocked

    status, answer = page.run(files=[("order.pdf", b"%PDF")])

    assert status == 500
    assert answer["error"]["code"] == "server_error"
    assert copied == {"env": True}
    assert list(solution.runs_root.iterdir()) == []
    assert page.get_json("/api/status")[1]["busy"] is False
    assert (page.poc / ".env").is_file()


# ---------------------------------------------------------------------------
# The steps, the page's own files and the source code
# ---------------------------------------------------------------------------

PAGE_ASSETS = (
    "ui/fonts/sora-latin-wght-normal.woff2",
    "ui/fonts/sora-latin-ext-wght-normal.woff2",
    "ui/fonts/OFL.txt",
    "ui/gaik.svg",
)


def _described(poc: Path) -> dict:
    return json.loads((poc / "ui" / "solution.json").read_text(encoding="utf-8"))


def _link(link: Path, target: Path) -> None:
    """A symlink, or a skip where this account may not make one (Windows)."""
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot make a symlink")


def test_the_steps_are_the_workflow_in_the_order_it_runs(tmp_path):
    bp = Blueprint.from_file(EXAMPLES / "incident_reporting_blueprint.json")
    in_order = [step.id for step in bp.workflow.steps]
    # The order comes from what each step depends on, not from the order they are written in.
    bp.workflow.steps.reverse()
    steps = _described(_scaffold(tmp_path, bp))["steps"]

    assert [step["id"] for step in steps] == in_order
    assert steps[0] == {
        "id": "record_observation",
        "title": "Record voice description and optional photo",
        "kind": "input",
        "uses": [],
        "gives": ["incident audio", "incident photo"],
    }
    assert steps[1] == {
        "id": "transcribe_audio",
        "title": "Transcribe audio recording",
        "kind": "ai",
        "component": "Transcriber",
        "uses": ["incident audio"],
        "gives": ["raw transcript"],
    }
    by_id = {step["id"]: step for step in steps}
    assert by_id["human_review"]["kind"] == "review"
    assert "component" not in by_id["human_review"]


def test_a_step_kind_follows_the_step_type_and_its_component(tmp_path):
    bp = Blueprint.from_file(EXAMPLES / "document_extraction_blueprint.json")
    upload, extract = bp.workflow.steps
    extract.component = None
    kinds = [step["kind"] for step in _described(_scaffold(tmp_path / "a", bp))["steps"]]
    assert kinds == ["input", "auto"]

    upload.type = "decision"
    extract.type = "something_new"
    kinds = [step["kind"] for step in _described(_scaffold(tmp_path / "b", bp))["steps"]]
    assert kinds == ["decision", "step"]


def test_hostile_step_text_is_inert_data_in_solution_json(tmp_path):
    bp = Blueprint.from_file(EXAMPLES / "document_extraction_blueprint.json")
    step = bp.workflow.steps[1]
    step.name = HOSTILE + "\nsecond line third"
    step.component = HOSTILE
    poc = _scaffold(tmp_path, bp)

    raw = (poc / "ui" / "solution.json").read_text(encoding="utf-8")
    assert not any(char in raw for char in "<>&  ")
    shown = json.loads(raw)["steps"][1]
    assert shown["title"] == HOSTILE + " second line third"
    assert shown["component"] == HOSTILE
    assert shown["uses"] == ["source pdf"]
    assert shown["gives"] == ["purchase order json"]
    # An artifact name with markup in it never reaches a package (the scaffolder
    # refuses the blueprint); the names are cut to plain one-line text all the same.
    assert _artifact_names(["a_b", HOSTILE + "\nx", "", 7]) == ["a b", HOSTILE + " x", "7"]
    assert _artifact_names(None) == []
    # The page and the server are still the templates.
    for written, template in (("ui/index.html", "ui/index.html"), ("app.py", "app.py.tmpl")):
        assert (poc / written).read_text("utf-8") == (COMMON / template).read_text("utf-8")


def test_a_blueprint_without_steps_gives_no_steps_and_the_page_shows_no_strip(tmp_path):
    bp = Blueprint.from_file(EXAMPLES / "document_extraction_blueprint.json")
    bp.workflow.steps = []
    assert _described(_scaffold(tmp_path, bp))["steps"] == []

    page = (COMMON / "ui" / "index.html").read_text(encoding="utf-8")
    # The strip is hidden in the markup and shown only when there is a step to show.
    assert '<section id="how" aria-labelledby="how-heading" hidden>' in page
    assert 'show($("how"), steps.length > 0)' in page


def test_the_pages_own_files_are_the_same_in_every_package(tmp_path):
    result = scaffold_poc(
        Blueprint.from_file(EXAMPLES / "document_extraction_blueprint.json"), tmp_path
    )
    poc = result["poc_dir"]

    for name in PAGE_ASSETS:
        assert poc / name in result["files"], name
        assert (poc / name).read_bytes() == (COMMON / name).read_bytes(), name
    # The font travels with its licence, and both font files are fonts.
    assert "SIL OPEN FONT LICENSE Version 1.1" in (poc / "ui/fonts/OFL.txt").read_text("utf-8")
    for name in PAGE_ASSETS[:2]:
        assert (poc / name).read_bytes()[:4] == b"wOF2", name
    page = (poc / "ui" / "index.html").read_text(encoding="utf-8")
    for name in (*PAGE_ASSETS[:2], PAGE_ASSETS[3]):
        assert f'"{name}"' in page, name


def test_the_fonts_and_the_mark_are_served(page):
    _, headers, _ = page.request("GET", "/")
    assert "font-src 'self'" in headers["Content-Security-Policy"]

    for name, content_type in (
        ("ui/fonts/sora-latin-wght-normal.woff2", "font/woff2"),
        ("ui/fonts/sora-latin-ext-wght-normal.woff2", "font/woff2"),
        ("ui/gaik.svg", "image/svg+xml"),
    ):
        status, headers, body = page.request("GET", "/" + name)
        assert status == 200, name
        assert headers["Content-Type"] == content_type
        assert headers["X-Content-Type-Options"] == "nosniff"
        # Opened as a document of its own, the file runs nothing.
        assert "default-src 'none'" in headers["Content-Security-Policy"]
        assert "script-src" not in headers["Content-Security-Policy"]
        assert body == (page.poc / name).read_bytes()

    assert page.request("GET", "/ui/gaik.svg", headers={"Host": "attacker.example"})[0] == 403


@pytest.mark.parametrize(
    "name",
    [
        "../app.py",
        "..%2Fapp.py",
        "%2e%2e/app.py",
        "..%5Capp.py",
        "fonts/../../.env",
        "fonts/..%2F..%2F.env",
        "fonts%5C..%5C..%5C.env",
        "fonts/%2e%2e/%2e%2e/config.yaml",
        "/etc/passwd",
        "%2Fetc%2Fpasswd",
        "..%2Fsecret.woff2",
        "fonts/..%2F..%2Fsecret.woff2",
        "fonts/.hidden.woff2",
        "fonts/OFL.txt",
        "fonts/missing.woff2",
        "fonts/",
        "solution.json",
        "index.html",
        "",
    ],
)
def test_the_assets_route_serves_the_pages_fonts_and_mark_only(page, name):
    (page.poc / ".env").write_text("AZURE_OPENAI_API_KEY=not-a-real-key\n", encoding="utf-8")
    # A file of a served kind outside ui/, and a hidden one inside it.
    (page.poc / "secret.woff2").write_bytes(b"wOF2 outside ui")
    (page.poc / "ui" / "fonts" / ".hidden.woff2").write_bytes(b"wOF2 hidden")

    status, _, body = page.request("GET", f"/ui/{name}")

    assert status == 404
    assert json.loads(body)["error"]["code"] == "not_found"
    assert b"not-a-real-key" not in body


def test_a_link_among_the_fonts_is_not_served(page, tmp_path):
    outside = tmp_path / "outside.woff2"
    outside.write_bytes(b"wOF2 from outside the package")
    _link(page.poc / "ui" / "fonts" / "linked.woff2", outside)

    assert page.request("GET", "/ui/fonts/linked.woff2")[0] == 404


def _source(page) -> tuple[dict, dict[str, bytes]]:
    """The source zip's response headers and its entries by name."""
    status, headers, body = page.request("GET", "/api/source")
    assert status == 200
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        assert archive.testzip() is None
        return headers, {name: archive.read(name) for name in archive.namelist()}


def test_the_source_zip_is_the_package_without_keys_inputs_and_results(page):
    poc = page.poc
    secret = "not-a-real-key-7f3a"
    for name in (".env", ".env.local", ".env.keys", "prod.env", "evals/.env"):
        (poc / name).write_text(f"AZURE_OPENAI_API_KEY={secret}\n", encoding="utf-8")
    (poc / "server.pem").write_text(secret, encoding="utf-8")
    (poc / "sample_input").mkdir(exist_ok=True)
    (poc / "sample_input" / "customer.pdf").write_bytes(b"%PDF " + secret.encode())
    (poc / "output" / "earlier_result.json").write_text(f'{{"k": "{secret}"}}', encoding="utf-8")
    for folder in ("__pycache__", "schemas/__pycache__", ".venv/Lib", "tryout", ".git", "venv"):
        (poc / folder).mkdir(parents=True, exist_ok=True)
    (poc / "__pycache__" / "run_poc.cpython-312.pyc").write_bytes(b"\x00")
    (poc / "schemas" / "__pycache__" / "output_schema.cpython-312.pyc").write_bytes(b"\x00")
    (poc / "schemas" / "stray.pyc").write_bytes(b"\x00")
    (poc / ".venv" / "pyvenv.cfg").write_text("home = x\n", encoding="utf-8")
    (poc / ".venv" / "Lib" / "site.py").write_text("# an environment's file\n", encoding="utf-8")
    # A virtual environment under a name of the user's own.
    (poc / "tryout" / "pyvenv.cfg").write_text("home = x\n", encoding="utf-8")
    (poc / "tryout" / "site.py").write_text("# an environment's file\n", encoding="utf-8")
    (poc / "venv" / "site.py").write_text("# an environment's file\n", encoding="utf-8")
    (poc / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    # Hidden files other than .env that hold credentials (review of #229) ...
    for name in (".netrc", ".npmrc", ".pypirc", ".git-credentials", "prompts/.netrc"):
        (poc / name).write_text(f"password {secret}\n", encoding="utf-8")
    # ... files whose name says they hold one, also where code and schemas live ...
    for name in (
        "credentials.json",
        "service-account.json",
        "secrets.toml",
        "id_rsa",
        "client_secret.json",
        "token.json",
        "schemas/credentials.json",
        "prompts/service_account.json",
        "api_secrets.py",
        # ... an API key's own name (second review of #229) ...
        "prompts/api_key.txt",
        "openai_apikey.json",
        "schemas/api-keys.yaml",
    ):
        (poc / name).write_text(f'{{"key": "{secret}"}}\n', encoding="utf-8")
    # ... the user's own ground truth for the evaluation ...
    (poc / "evals" / "ground_truth" / "order_1042.json").write_text(
        f'{{"customer": "{secret}"}}', encoding="utf-8"
    )
    (poc / "evals" / "ground_truth" / "check.py").write_text(f"# {secret}\n", encoding="utf-8")
    # ... also where the folder's name is written in another case: on Windows and
    # macOS it is the same folder (second review of #229).
    (poc / "Evals" / "Ground_Truth").mkdir(parents=True, exist_ok=True)
    (poc / "Evals" / "Ground_Truth" / "case_2.py").write_text(f"# {secret}\n", encoding="utf-8")
    # ... and a file nobody thought of: not code, a setting or a schema.
    (poc / "notes.md").write_text(f"The user's own note: {secret}\n", encoding="utf-8")
    (poc / "ui" / "notes.txt").write_text(secret, encoding="utf-8")
    # A run before the download: its working folder and uploads are not the package's.
    assert page.run(files=[("order.pdf", b"%PDF " + secret.encode())])[0] == 200

    headers, files = _source(page)
    # Written by the scaffolder where the installed gaik has saved_schema (not in
    # CI, which installs the wizard without gaik): it is the package's own schema.
    with_gaik = ["schemas/output_schema_model.json"]
    from_gaik = [name for name in with_gaik if (poc / name).is_file()]

    assert headers["Content-Type"] == "application/zip"
    assert (
        headers["Content-Disposition"]
        == 'attachment; filename="purchase_order_extraction-source.zip"'
    )
    assert headers["X-Content-Type-Options"] == "nosniff"
    folder = "purchase_order_extraction-source/"
    assert all(name.startswith(folder) for name in files)
    assert {name.removeprefix(folder) for name in files} == {
        ".env.example",
        "README.md",
        "app.py",
        "config.yaml",
        "document_manifest.py",
        "input_bundle.py",
        "poc_output.py",
        "provider_config.py",
        "requirements.txt",
        "run_poc.py",
        "evals/run_basic_eval.py",
        "prompts/extraction_requirements.md",
        "schemas/output_schema.json",
        "schemas/output_schema.py",
        "schemas/output_schema_requirements.json",
        "ui/index.html",
        "ui/solution.json",
        *PAGE_ASSETS,
        *from_gaik,
    }
    assert not any(secret.encode() in content for content in files.values())
    # What is in the zip is the package's files, byte for byte.
    for name in ("app.py", "run_poc.py", "ui/index.html", "ui/fonts/sora-latin-wght-normal.woff2"):
        assert files[folder + name] == (poc / name).read_bytes(), name


def test_a_link_in_the_package_is_not_in_the_source_zip(page, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "id_rsa.txt").write_text("a file outside the package", encoding="utf-8")
    _link(page.poc / "linked.txt", outside / "id_rsa.txt")
    _link(page.poc / "linked_folder", outside)
    _link(page.poc / "prompts" / "linked.md", outside / "id_rsa.txt")

    _, files = _source(page)

    assert any(name.endswith("/run_poc.py") for name in files)
    assert not any("linked" in name or "id_rsa" in name for name in files)
    assert not any(b"outside the package" in content for content in files.values())


def test_a_file_too_large_to_be_source_code_is_left_out(page):
    (page.poc / "table_data.py").write_bytes(b"#" * (page.app.MAX_SOURCE_FILE_BYTES + 1))

    _, files = _source(page)

    assert not any(name.endswith("table_data.py") for name in files)
    assert any(name.endswith("/run_poc.py") for name in files)


def test_the_zips_page_files_are_the_ones_the_scaffolder_writes(page):
    """app.py lists the page's files itself; it must name what the scaffolder writes."""
    from solution_wizard.scaffolder import _PAGE_ASSETS, TEST_PAGE_TEMPLATES

    written = {name.removeprefix("ui/") for name in TEST_PAGE_TEMPLATES if name.startswith("ui/")}
    assert page.app._PAGE_FILES == written | set(_PAGE_ASSETS) | {"solution.json"}
    _, files = _source(page)
    assert {name.split("/", 1)[1] for name in files if "/ui/" in name} == {
        f"ui/{name}" for name in page.app._PAGE_FILES
    }


def test_a_file_with_a_second_hard_link_is_not_in_the_source_zip(page, tmp_path):
    """A hard link is a file from elsewhere under a name of the package's."""
    outside = tmp_path / "outside.py"
    outside.write_text("# a file outside the package\n", encoding="utf-8")
    try:
        os.link(outside, page.poc / "helper.py")
    except (OSError, NotImplementedError):
        pytest.skip("this file system cannot make a hard link")

    _, files = _source(page)

    assert not any(name.endswith("/helper.py") for name in files)
    assert any(name.endswith("/run_poc.py") for name in files)


def test_a_package_over_the_size_limit_is_refused_not_cut_short(page, monkeypatch):
    """The zip is built in memory: there is a limit on what it holds in all."""
    sizes = sorted(
        (page.poc / name).stat().st_size for name, _ in page.server.solution.source_files()
    )
    monkeypatch.setattr(page.app, "MAX_SOURCE_BYTES", sum(sizes) - 1)

    status, _, body = page.request("GET", "/api/source")

    assert status == 413
    assert json.loads(body)["error"]["code"] == "too_large"

    monkeypatch.setattr(page.app, "MAX_SOURCE_BYTES", sum(sizes))
    assert page.request("GET", "/api/source")[0] == 200


def test_a_head_request_does_not_build_the_zip(page, monkeypatch):
    def not_built():
        raise AssertionError("HEAD built the zip")

    monkeypatch.setattr(page.server.solution, "source_zip", not_built)

    status, headers, body = page.request("HEAD", "/api/source")

    assert status == 200
    assert body == b""
    assert headers["Content-Type"] == "application/zip"
    assert headers["Content-Disposition"].startswith("attachment;")
    assert "Content-Length" not in headers


def test_the_source_download_is_on_while_the_server_listens_on_this_computer_only(page):
    assert page.server.source_download is True
    assert page.get_json("/api/solution")[1]["source_download"] is True
    assert page.request("GET", "/api/source")[0] == 200
    # The page shows its download only while the server says it is on.
    html = (COMMON / "ui" / "index.html").read_text(encoding="utf-8")
    assert 'show($("source"), solution.source_download !== false)' in html


@pytest.mark.skipif(
    os.name == "nt",
    reason="listening on every address makes the Windows firewall ask for leave on screen",
)
def test_the_source_download_is_off_while_the_server_listens_on_the_network(tmp_path):
    """With --host, /api/source handed the package tree to anyone who could reach it."""
    served = Page(_scaffold(tmp_path), host="0.0.0.0")
    try:
        assert served.server.source_download is False
        for method in ("GET", "HEAD"):
            status, _, body = served.request(method, "/api/source")
            assert status == 403, method
        status, _, body = served.request("GET", "/api/source")
        assert json.loads(body)["error"] == {
            "code": "source_off",
            "message": (
                "The source code download is off while the test page listens on the network "
                "(--host). Start it without --host to download the source code."
            ),
        }
        assert served.get_json("/api/solution")[1]["source_download"] is False
        # The rest of the page works as before.
        assert served.request("GET", "/")[0] == 200
    finally:
        served.close()


@pytest.mark.parametrize(
    ("address", "loopback"),
    [
        ("127.0.0.1", True),
        ("127.0.0.2", True),
        ("::1", True),
        ("0.0.0.0", False),
        ("::", False),
        ("192.168.1.20", False),
        ("fe80::1%eth0", False),
        ("", False),
    ],
)
def test_only_a_loopback_address_keeps_the_source_download(page, address, loopback):
    assert page.app._is_loopback(address) is loopback


@pytest.mark.parametrize(
    ("solution_id", "name"),
    [
        ('../..\\evil"\r\nSet-Cookie: x=1', "evil-Set-Cookie-x-1-source.zip"),
        ("työ aika", "ty-aika-source.zip"),
        ("", "solution-source.zip"),
        (None, "solution-source.zip"),
    ],
)
def test_the_source_zip_is_named_after_the_solution_in_safe_characters(page, solution_id, name):
    described = _described(page.poc)
    described["id"] = solution_id
    (page.poc / "ui" / "solution.json").write_text(json.dumps(described), encoding="utf-8")

    headers, files = _source(page)

    assert headers["Content-Disposition"] == f'attachment; filename="{name}"'
    assert "Set-Cookie" not in headers
    assert all(entry.startswith(name.removesuffix(".zip") + "/") for entry in files)


def test_a_page_on_another_site_cannot_take_the_source(page):
    assert page.request("GET", "/api/source", headers={"Host": "attacker.example"})[0] == 403
    foreign = {"Origin": "https://attacker.example"}
    assert page.request("GET", "/api/source", headers=foreign)[0] == 403
    own = {"Origin": f"http://127.0.0.1:{page.port}"}
    assert page.request("GET", "/api/source", headers=own)[0] == 200


def test_the_page_links_the_source_download_and_the_readme_names_it(tmp_path):
    page = (COMMON / "ui" / "index.html").read_text(encoding="utf-8")
    assert 'href="/api/source" download' in page
    assert "Download source code" in page
    assert "Lataa lähdekoodi" in page

    readme = (_scaffold(tmp_path) / "README.md").read_text(encoding="utf-8")
    assert "GET /api/source" in readme


# ---------------------------------------------------------------------------
# Second review (17 Nov 2026): stop signals, --host and a busy server
# ---------------------------------------------------------------------------


def _wait_until_busy(served: Page) -> None:
    deadline = time.monotonic() + 20
    while not served.get_json("/api/status")[1]["busy"]:
        assert time.monotonic() < deadline, "the first run never started"
        time.sleep(0.05)


def test_a_busy_server_refuses_a_second_run_before_it_reads_the_body(page, monkeypatch):
    """Parallel posts each held up to the upload limit in memory before the busy refusal.

    Every read of a request's body is recorded: the refused request's body is read
    away a piece at a time and dropped, never held whole and never parsed.
    """
    reads: list[list[int]] = []
    handler_class = page.app.Handler
    setup = handler_class.setup

    class Recording:
        """The request's rfile, with the size of every read() kept in ``log``."""

        def __init__(self, raw, log):
            self._raw, self._log = raw, log

        def read(self, size=-1):
            data = self._raw.read(size)
            self._log.append(len(data))
            return data

        def __getattr__(self, name):
            return getattr(self._raw, name)

    def recording_setup(handler):
        setup(handler)
        log: list[int] = []
        reads.append(log)
        handler.rfile = Recording(handler.rfile, log)

    monkeypatch.setattr(handler_class, "setup", recording_setup)
    parsed = []
    parse = page.app.parse_multipart

    def counting(content_type, body):
        parsed.append(len(body))
        return parse(content_type, body)

    monkeypatch.setattr(page.app, "parse_multipart", counting)
    first = {}
    thread = threading.Thread(
        target=lambda: first.update(answer=page.run(files=[("slow.pdf", b"%PDF")]))
    )
    thread.start()
    _wait_until_busy(page)

    refused = 3 * 1024 * 1024
    status, answer = page.run(files=[("order.pdf", b"x" * refused)])
    thread.join(timeout=60)

    assert status == 409
    assert answer["error"] == {
        "code": "busy",
        "message": "A run is already going. Wait for it to finish.",
    }
    # The refused body was read away in pieces of at most 1 MiB, all of it, so the
    # answer reaches the browser; no read held more than one piece.
    (pieces,) = [log for log in reads if sum(log) > refused]
    assert max(pieces) <= 1024 * 1024
    assert len(pieces) >= 3
    # Only the first request's body was read whole and parsed.
    assert len(parsed) == 1
    assert first["answer"][0] == 200 and first["answer"][1]["ok"] is True
    # A refused request gives the run back: the next one runs.
    status, _, _ = page.request(
        "POST", "/api/run", body=b"{}", headers={"Content-Type": "application/json"}
    )
    assert status == 415
    assert page.run(files=[("order.pdf", b"%PDF")])[0] == 200


def test_no_run_starts_once_the_server_is_stopping(page):
    """A run that started after close() would outlive the server, keys and all."""
    page.server.solution.close()

    status, answer = page.run(files=[("order.pdf", b"%PDF")])

    assert status == 503
    assert answer["error"]["code"] == "stopping"
    assert not page.server.solution.runs_root.exists()


def test_with_another_address_the_host_check_stays_on(tmp_path):
    """With --host the check was off: any site's name pointed at this computer got in."""
    try:
        served = Page(_scaffold(tmp_path), host="127.0.0.2")
    except OSError:
        pytest.skip("127.0.0.2 cannot be listened on here")
    try:
        port = served.port
        for foreign in ("attacker.example", f"attacker.example:{port}", ""):
            status, _, body = served.request("GET", "/api/solution", headers={"Host": foreign})
            assert status == 403, foreign
            assert json.loads(body)["error"]["code"] == "forbidden"
        for own in (f"127.0.0.2:{port}", f"localhost:{port}", f"127.0.0.1:{port}"):
            assert served.request("GET", "/api/solution", headers={"Host": own})[0] == 200, own
    finally:
        served.close()


def test_listening_on_every_address_takes_this_computers_names_and_addresses(page):
    app = page.app
    every = app._host_names("0.0.0.0", "0.0.0.0")

    assert {"localhost", "127.0.0.1", "::1"} <= every
    assert "0.0.0.0" not in every
    # Another computer reaches the page by an address of this one, or by its name.
    for host in ("192.168.1.20", "10.0.0.5", "fe80::1%eth0", socket.gethostname().lower()):
        assert app._host_allowed(host, every, True), host
    # Only a site's own name can be put there by its page, and that is refused.
    for host in ("attacker.example", "192.168.1.20.nip.io", ""):
        assert not app._host_allowed(host, every, True), host
    # The unspecified and group addresses are no address of this computer's.
    for host in ("0.0.0.0", "::", "224.0.0.1", "239.255.255.250", "ff02::1"):
        assert not app._host_allowed(host, every, True), host

    # Listening on one address, another address is not this server's.
    one = app._host_names("192.168.1.20", "192.168.1.20")
    assert app._host_allowed("192.168.1.20", one, False)
    assert app._host_allowed("localhost", one, False)
    assert not app._host_allowed("10.0.0.5", one, False)
    assert not app._host_allowed("attacker.example", one, False)


@pytest.mark.parametrize(
    "header",
    [
        # Read as a URL's authority, each of these is 127.0.0.1 or localhost.
        "attacker.example@127.0.0.1:{port}",
        "attacker.example:x@localhost:{port}",
        "127.0.0.1:{port}/attacker.example",
        "127.0.0.1:{port}?attacker.example",
        "127.0.0.1:{port}#attacker.example",
        "127.0.0.1\\attacker.example:{port}",
        # More than one port, a port that is not a number, white space.
        "127.0.0.1:{port}:{port}",
        "localhost:http",
        "127.0.0.1 :{port}",
        "127.0.0.1\t:{port}",
        # A bracketed address that does not end, or with more after it.
        "[::1",
        "[::1]{port}",
        "[::1]:{port}:1",
    ],
)
def test_a_host_header_that_is_more_than_a_name_and_a_port_is_refused(page, header):
    status, _, body = page.request(
        "GET", "/api/solution", headers={"Host": header.format(port=page.port)}
    )

    assert status == 403, header
    assert json.loads(body)["error"]["code"] == "forbidden"


def test_a_host_header_with_a_name_and_a_port_is_read_as_that_name(page):
    app = page.app
    assert app._host_name("LocalHost:8000") == "localhost"
    assert app._host_name("127.0.0.1") == "127.0.0.1"
    assert app._host_name("[::1]:8000") == "::1"
    assert app._host_name("[fe80::1%25eth0]") == "fe80::1%25eth0"
    assert app._host_name("attacker.example@127.0.0.1:8000") == ""
    assert app._host_name("") == ""
    for own in (f"[::1]:{page.port}", f"LOCALHOST:{page.port}", "127.0.0.1"):
        assert page.request("GET", "/api/solution", headers={"Host": own})[0] == 200, own


#: The signals that stop the server, with what this platform can send to test them,
#: and whether the same signal keeps coming while the server cleans up.
_STOP_SIGNALS = (
    [("CTRL_BREAK_EVENT", False), ("CTRL_BREAK_EVENT", True)]
    if os.name == "nt"
    else [
        ("SIGINT", False),
        ("SIGTERM", False),
        ("SIGHUP", False),
        ("SIGINT", True),
        ("SIGTERM", True),
    ]
)


def _post_and_ignore(port):
    try:
        _post_run("127.0.0.1", port, files=[("tree.pdf", b"%PDF")])
    except (OSError, ValueError, http.client.HTTPException):
        pass  # the server stops during the run


@pytest.mark.parametrize(("sent", "again"), _STOP_SIGNALS)
def test_a_stop_signal_stops_the_run_and_removes_its_working_folder(tmp_path, sent, again):
    """SIGTERM or SIGHUP ended Python at once: the run's copy of .env stayed in the
    temporary folder and run_poc.py, in a session of its own, went on.

    ``again``: the signal is sent every few milliseconds until the server has gone.
    A second Ctrl+C during the cleanup raised KeyboardInterrupt inside it and left
    the run's process and folder behind (second review of #220).
    """
    poc = _scaffold(tmp_path / "package")
    (poc / "run_poc.py").write_text(FAKE_RUN_POC, encoding="utf-8")
    (poc / ".env").write_text("EXAMPLE_SETTING=1\n", encoding="utf-8")
    temp = tmp_path / "temp"
    temp.mkdir()
    pid_file = tmp_path / "child.pid"
    env = {
        **os.environ,
        "TMPDIR": str(temp),
        "TEMP": str(temp),
        "TMP": str(temp),
        "POC_TEST_PIDFILE": str(pid_file),
        "PYTHONUNBUFFERED": "1",
    }
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    server = subprocess.Popen(
        [sys.executable, "app.py", "--port", "0"],
        cwd=poc,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        creationflags=flags,
    )
    child = None
    try:
        first = server.stdout.readline()
        assert first.startswith("Test page: http://127.0.0.1:"), first
        port = int(first.strip().rsplit(":", 1)[1])
        threading.Thread(target=_post_and_ignore, args=(port,), daemon=True).start()
        deadline = time.monotonic() + 30
        while not (pid_file.exists() and pid_file.read_text(encoding="utf-8")):
            assert server.poll() is None, server.stdout.read()
            assert time.monotonic() < deadline, "the run never started its own process"
            time.sleep(0.1)
        child = int(pid_file.read_text(encoding="utf-8"))
        assert list(temp.glob("poc-test-page-*/*/.env")), "the run has its copy of the keys"

        server.send_signal(getattr(signal, sent))
        deadline = time.monotonic() + 30
        while again and server.poll() is None and time.monotonic() < deadline:
            try:
                server.send_signal(getattr(signal, sent))
            except OSError:
                break  # it has just gone
            time.sleep(0.005)
        server.wait(timeout=30)
        log = server.stdout.read()
    finally:
        if server.poll() is None:
            server.kill()
            server.wait(timeout=10)
        server.stdout.close()

    deadline = time.monotonic() + 10
    while child is not None and _is_running(child) and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not _is_running(child), "the entrypoint's own process outlived the server"
    assert list(temp.iterdir()) == []
    # It stopped on its own, through its cleanup, with nothing raised in it.
    assert server.returncode == 0, log
    assert "Stopped." in log and "Traceback" not in log


# ---------------------------------------------------------------------------
# Second review, round 2 (17 Nov 2026): the package's own modules, a stalled request
# ---------------------------------------------------------------------------


def test_a_module_in_the_package_does_not_stand_in_for_the_standard_library(tmp_path):
    """``python app.py`` puts the package's folder first on sys.path.

    An ipaddress.py there was imported in place of the library's, so a file the
    agent wrote changed what the unchanged server does (its Host check, here).
    """
    poc = _scaffold(tmp_path / "package")
    marker = tmp_path / "shadow-ran"
    (poc / "ipaddress.py").write_text(
        f"open({str(marker)!r}, 'w').close()\nraise SystemExit(7)\n", encoding="utf-8"
    )
    temp = tmp_path / "temp"
    temp.mkdir()
    env = {**os.environ, "TMPDIR": str(temp), "TEMP": str(temp), "TMP": str(temp)}
    server = subprocess.Popen(
        [sys.executable, "app.py", "--port", "0"],
        cwd=poc,
        env={**env, "PYTHONUNBUFFERED": "1"},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    # A server that never prints its address is stopped, so the read below ends.
    stop = threading.Timer(30, server.kill)
    stop.start()
    try:
        first = server.stdout.readline()
        stop.cancel()
        if not first.startswith("Test page: http://127.0.0.1:"):
            server.kill()
            pytest.fail(f"the server did not start: {first}{server.stdout.read()}")
        port = int(first.strip().rsplit(":", 1)[1])
        assert _request("127.0.0.1", port, "GET", "/api/solution")[0] == 200
        status, _, _ = _request(
            "127.0.0.1", port, "GET", "/api/solution", headers={"Host": "attacker.example"}
        )
        assert status == 403
    finally:
        stop.cancel()
        server.kill()
        server.wait(timeout=10)
        server.stdout.close()
    assert not marker.exists()


def _stalled_post(served: Page, sent: bytes, length: int) -> socket.socket:
    """A POST /api/run that says ``length`` bytes are coming and sends ``sent`` of them."""
    connection = socket.create_connection((served.address, served.port), timeout=30)
    connection.sendall(
        (
            "POST /api/run HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{served.port}\r\n"
            "Content-Type: multipart/form-data; boundary=x\r\n"
            f"Content-Length: {length}\r\n\r\n"
        ).encode()
        + sent
    )
    return connection


def _answer(connection: socket.socket) -> tuple[int, dict]:
    response = http.client.HTTPResponse(connection)
    response.begin()
    return response.status, json.loads(response.read())


def test_a_request_that_stops_sending_gives_the_run_back(page, monkeypatch):
    """The run was taken before the body was read and no read had a time limit, so
    a connection that stopped sending held it while /api/status said it was free.
    """
    monkeypatch.setattr(page.app.Handler, "timeout", 1)
    stalled = _stalled_post(page, b"--x\r\n", 10_000)
    try:
        deadline = time.monotonic() + 5
        while not page.get_json("/api/status")[1]["busy"]:
            assert time.monotonic() < deadline, "the stalled request never held the run"
            time.sleep(0.05)
        assert page.run(files=[("order.pdf", b"%PDF")])[0] == 409

        status, answer = _answer(stalled)
    finally:
        stalled.close()

    assert status == 408
    assert answer["error"]["code"] == "too_slow"
    assert page.get_json("/api/status")[1]["busy"] is False
    assert page.run(files=[("order.pdf", b"%PDF")])[0] == 200


def test_files_that_trickle_in_are_refused_once_they_take_too_long(page, monkeypatch):
    """A byte every so often never tripped a wait for the next one."""
    monkeypatch.setattr(page.app.Handler, "timeout", 2)
    monkeypatch.setattr(page.app, "BODY_TIMEOUT_SECONDS", 1)
    trickling = _stalled_post(page, b"-", 10_000)
    started = time.monotonic()
    try:
        trickling.settimeout(0.2)
        status = None
        while status is None:
            assert time.monotonic() - started < 15, "the trickle was never cut off"
            try:
                trickling.sendall(b"-")
            except OSError:
                pass  # the server has answered and closed its end
            try:
                if trickling.recv(1, socket.MSG_PEEK):
                    trickling.settimeout(10)
                    status, answer = _answer(trickling)
            except TimeoutError:
                pass
    finally:
        trickling.close()

    assert status == 408
    assert answer["error"]["code"] == "too_slow"
    assert page.get_json("/api/status")[1]["busy"] is False
    assert page.run(files=[("order.pdf", b"%PDF")])[0] == 200


# ---------------------------------------------------------------------------
# Second review of #229, round 2 (17 Nov 2026)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "relative",
    [
        "Sample_Input/notes.py",
        "OUTPUT/result.py",
        "Evals/Ground_Truth/case.py",
        "EVALS/GROUND_TRUTH/case.py",
        "Venv/Lib/site.py",
        "schemas/__PYCACHE__/x.py",
        "prompts/API_KEY.txt",
        "ApiKey.py",
    ],
)
def test_a_folder_or_name_in_another_case_is_not_source_either(page, relative):
    """Compared case by case, Output/ on Windows or macOS was not output/."""
    assert page.app._is_source(PurePosixPath(relative)) is False


def test_code_named_like_a_key_word_is_still_source(page):
    for relative in ("tokenizer.py", "keyword_rules.py", "schemas/output_schema.py", "api.py"):
        assert page.app._is_source(PurePosixPath(relative)) is True, relative


def test_an_env_example_that_gives_a_key_a_value_is_not_in_the_source_zip(page):
    """The value check wizard_api makes on .env.example was not made here."""
    example = page.poc / ".env.example"
    folder = "purchase_order_extraction-source/"
    template = example.read_text(encoding="utf-8")

    example.write_text(template + "AZURE_OPENAI_API_KEY=not-a-real-key-7f3a\n", encoding="utf-8")
    _, files = _source(page)
    assert folder + ".env.example" not in files
    assert not any(b"not-a-real-key-7f3a" in content for content in files.values())

    # Saved with a byte order mark, as Windows editors do, or in UTF-16: the key on
    # the first line was missed (found by a second reader on #229, round 2).
    for written in (
        b"\xef\xbb\xbfAZURE_OPENAI_API_KEY=not-a-real-key-7f3a\n",
        "AZURE_OPENAI_API_KEY=not-a-real-key-7f3a\n".encode("utf-16"),
    ):
        example.write_bytes(written)
        _, files = _source(page)
        assert folder + ".env.example" not in files, written[:4]

    placeholders = "AZURE_OPENAI_API_KEY=<your key>\nHF_TOKEN=\n# OPENAI_API_KEY=xxxx\n"
    example.write_text(template + placeholders + "MAX_TOKENS=4000\n", encoding="utf-8")
    _, files = _source(page)
    assert files[folder + ".env.example"] == example.read_bytes()


@pytest.mark.parametrize(
    ("text", "valued"),
    [
        ("AZURE_OPENAI_API_KEY=\n", []),
        ("AZURE_OPENAI_API_KEY=abc123\n", ["AZURE_OPENAI_API_KEY"]),
        ("export HF_TOKEN='hf_abc'\n", ["HF_TOKEN"]),
        ("# CLIENT_SECRET=s3cr3t\n", ["CLIENT_SECRET"]),
        ("OPENAI_API_KEY=your-key-here\n", []),
        ("OPENAI_API_KEY=<key>\n", []),
        ("OPENAI_API_KEY=xxxx  # put yours here\n", []),
        ("OPENAI_API_KEY=  # a comment\n", []),
        ('OPENAI_API_KEY="abc" # quoted\n', ["OPENAI_API_KEY"]),
        ("GOOGLE_SERVICE_ACCOUNT_JSON={}\n", ["GOOGLE_SERVICE_ACCOUNT_JSON"]),
        ("MAX_TOKENS=4000\nKEYWORDS=a,b\nAZURE_OPENAI_API_VERSION=2024-10-21\n", []),
    ],
)
def test_the_env_example_check_reads_keys_as_wizard_api_does(page, text, valued):
    """The rule of wizard_api's poc_service.env_example_key_values; its tests hold the two equal."""
    assert page.app._env_example_key_values(text) == valued


def test_a_head_request_is_refused_as_get_is_over_the_limits(page, monkeypatch):
    """HEAD answered 200 for a package GET refuses with 413."""
    monkeypatch.setattr(page.app, "MAX_SOURCE_FILES", 1)

    status, _, _ = page.request("HEAD", "/api/source")
    assert status == 413
    assert page.request("GET", "/api/source")[0] == 413


def _can_listen_on(address: str) -> bool:
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as probe:
            probe.bind((address, 0))
    except (AttributeError, OSError):
        return False
    return True


def test_an_ipv6_loopback_address_is_listened_on(tmp_path):
    """--host ::1 failed to start: the server listened on IPv4 only."""
    if not _can_listen_on("::1"):
        pytest.skip("::1 cannot be listened on here")
    served = Page(_scaffold(tmp_path), host="::1")
    try:
        assert served.server.address_family == socket.AF_INET6
        status, _, body = served.request("GET", "/api/solution")
        assert status == 200
        assert json.loads(body)["source_download"] is True
        assert served.request("GET", "/api/source")[0] == 200
        # The Host check holds on IPv6 as well.
        status, _, _ = served.request("GET", "/", headers={"Host": "attacker.example"})
        assert status == 403
    finally:
        served.close()


def _dual_stack_here() -> bool:
    """Whether an IPv6 socket on every address takes IPv4 connections on this system."""
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as listener:
            listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            listener.bind(("::", 0))
            listener.listen(1)
            with socket.create_connection(("127.0.0.1", listener.getsockname()[1]), timeout=5):
                return True
    except (AttributeError, OSError):
        return False


@pytest.mark.skipif(
    os.name == "nt",
    reason="listening on every address makes the Windows firewall ask for leave on screen",
)
@pytest.mark.parametrize("ipv6_only", [False, True])
def test_every_ipv6_address_answers_at_the_address_printed_and_has_no_source_download(
    tmp_path, monkeypatch, ipv6_only
):
    """Where the system has no dual stack, --host :: printed 127.0.0.1, which did not
    answer (second reader on #229, round 2). ``ipv6_only`` makes the dual stack fail."""
    if not _can_listen_on("::"):
        pytest.skip(":: cannot be listened on here")
    dual_stack = _dual_stack_here() and not ipv6_only
    if ipv6_only:
        # No such option: setting it fails, as on a system without a dual stack.
        monkeypatch.setattr(socket, "IPV6_V6ONLY", -1)
    served = Page(_scaffold(tmp_path), host="::")
    try:
        assert served.server.dual_stack is dual_stack
        served.address = served.app._shown_host("::", served.server).strip("[]")
        assert served.address == ("127.0.0.1" if dual_stack else "::1")
        assert served.request("GET", "/")[0] == 200
        assert served.server.source_download is False
        assert served.request("GET", "/api/source")[0] == 403
    finally:
        served.close()


class _Connection:
    """The socket under a handler: what each read was allowed to wait."""

    def __init__(self):
        self.timeouts = []

    def settimeout(self, seconds):
        self.timeouts.append(seconds)


def test_no_read_of_the_files_waits_past_their_deadline(page, monkeypatch):
    """The last read could wait the connection's full timeout after the deadline, and a
    body that ended then was taken (found by a second reader on #220, round 2)."""
    app = page.app
    clock = {"now": 0.0}
    monkeypatch.setattr(app.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(app, "BODY_TIMEOUT_SECONDS", 300)

    def late_piece(size):
        # The first piece comes 295 s in; the last one only after the deadline.
        clock["now"] += 295 if clock["now"] == 0 else 10
        return b"x"

    handler = types.SimpleNamespace(
        rfile=types.SimpleNamespace(read1=late_piece),
        connection=_Connection(),
        timeout=30,
        close_connection=False,
    )
    with pytest.raises(app.RefusalError) as refused:
        app.Handler._read_body(handler, 2)

    assert (refused.value.status, refused.value.code) == (408, "too_slow")
    assert handler.close_connection is True
    # The second wait was held to the 5 s left, and the timeout is put back after.
    assert handler.connection.timeouts == [30, 5, 30]


@pytest.mark.parametrize(
    ("host", "dual_stack", "shown"),
    [
        ("127.0.0.1", False, "127.0.0.1"),
        ("0.0.0.0", False, "127.0.0.1"),
        ("::", True, "127.0.0.1"),
        # Listening on IPv6 alone, 127.0.0.1 does not answer (round 2 of #229).
        ("::", False, "[::1]"),
        ("::1", False, "[::1]"),
        ("192.168.1.20", False, "192.168.1.20"),
    ],
)
def test_the_address_printed_is_one_that_answers(page, host, dual_stack, shown):
    server = types.SimpleNamespace(dual_stack=dual_stack)
    assert page.app._shown_host(host, server) == shown
