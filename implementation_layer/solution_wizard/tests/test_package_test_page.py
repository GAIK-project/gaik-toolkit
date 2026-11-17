"""Every generated package carries a test page: app.py, ui/index.html and ui/solution.json.

The server and the page are fixed files; the blueprint reaches them only as data in
ui/solution.json. The server is started here on a free port against a stand-in
run_poc.py that makes no model call.
"""

import ast
import hashlib
import http.client
import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from solution_wizard.blueprint import Blueprint  # noqa: E402
from solution_wizard.scaffolder import scaffold_poc  # noqa: E402
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
# Second review (17 Nov 2026): stop signals, --host and a busy server
# ---------------------------------------------------------------------------


def _wait_until_busy(served: Page) -> None:
    deadline = time.monotonic() + 20
    while not served.get_json("/api/status")[1]["busy"]:
        assert time.monotonic() < deadline, "the first run never started"
        time.sleep(0.05)


def test_a_busy_server_refuses_a_second_run_before_it_reads_the_body(page, monkeypatch):
    """Parallel posts each held up to the upload limit in memory before the busy refusal."""
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

    status, answer = page.run(files=[("order.pdf", b"x" * 200_000)])
    thread.join(timeout=60)

    assert status == 409
    assert answer["error"] == {
        "code": "busy",
        "message": "A run is already going. Wait for it to finish.",
    }
    # Only the first request's body was read and parsed.
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

    # Listening on one address, another address is not this server's.
    one = app._host_names("192.168.1.20", "192.168.1.20")
    assert app._host_allowed("192.168.1.20", one, False)
    assert app._host_allowed("localhost", one, False)
    assert not app._host_allowed("10.0.0.5", one, False)
    assert not app._host_allowed("attacker.example", one, False)


#: The signals that stop the server, with what this platform can send to test them.
_STOP_SIGNALS = ["CTRL_BREAK_EVENT"] if os.name == "nt" else ["SIGTERM", "SIGHUP"]


def _post_and_ignore(port):
    try:
        _post_run("127.0.0.1", port, files=[("tree.pdf", b"%PDF")])
    except (OSError, ValueError, http.client.HTTPException):
        pass  # the server stops during the run


@pytest.mark.parametrize("sent", _STOP_SIGNALS)
def test_a_stop_signal_stops_the_run_and_removes_its_working_folder(tmp_path, sent):
    """SIGTERM or SIGHUP ended Python at once: the run's copy of .env stayed in the
    temporary folder and run_poc.py, in a session of its own, went on."""
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
        server.wait(timeout=30)
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
