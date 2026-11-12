"""Live smoke test of the demo API: one small real request per use case.

It answers one question after a build, a deployment or a gaik release: do the demo's
use cases still work end to end with the gaik that is installed and the model that is
configured? Each check sends a few lines of synthetic text through the real route and
looks at the answer. Nothing is mocked, so it needs the provider keys the API needs.

Run it where the API runs:

    python -m api.smoke                    from toolkit_demo_app/, local environment
    python smoke.py                        in the API image (its working directory is api/)
    oc exec -n <namespace> deployment/gaik-demo-api -- python smoke.py     after a rollout

Options: ``--list`` names the checks, ``--only a,b`` runs some of them, ``--json FILE``
writes the report. The exit code is 0 only when every selected check passed.

The app is called in process, so no sign-in is involved and the running server is not
touched. A check gets a second attempt when the first one fails, because a single model
answer can be off; the report shows the attempts, so a check that needs two is visible.
The report holds check names, timings and short reasons, never keys or provider replies.

Adding a use case: write a ``check_<name>(client)`` function that raises
``AssertionError`` with a short reason, and add it to ``CHECKS``.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
from collections.abc import Callable

ATTEMPTS = 2

PURCHASE_ORDER = (
    "Purchase order PO-7741 was placed on 2 August 2026 by Northwind Tools Oy.\n"
    "Delivery is due on 10 August 2026.\n"
)
EXTRACTION_TASK = (
    "Extract these fields from a purchase order.\n\n"
    "- `po_number`: the purchase order number as written.\n"
    "- `order_date`: the date the order was placed.\n"
    "- `delivery_date`: the delivery date, formatted `DD/MM/YYYY` (for example `05/03/2027`).\n"
)
INVOICE = (
    "INVOICE\n\nInvoice number: INV-2026-0042\nInvoice date: 3 August 2026\n"
    "Bill to: Northwind Tools Oy\n\n2 x torque wrench, 120.00 EUR each\n"
    "Total due: 240.00 EUR. Payment terms: 14 days net.\n"
)
ORDER_LINES_CSV = "item,quantity,unit_price\nwrench,10,12.50\nhammer,12,8.00\npliers,20,6.25\n"


def _expect(condition: bool, reason: str) -> None:
    if not condition:
        raise AssertionError(reason)


def _json(response, where: str) -> dict:
    """The JSON body of a 200 response; anything else fails the check with the status."""
    if response.status_code != 200:
        try:
            detail = str(response.json().get("detail", ""))[:160]
        except Exception:  # noqa: BLE001 - a non-JSON error body is reported by status alone
            detail = ""
        raise AssertionError(f"{where} returned HTTP {response.status_code} {detail}".strip())
    return response.json()


def _pdf(text: str) -> bytes:
    """A one-page PDF with a text layer."""
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(fitz.Rect(50, 50, 550, 750), text, fontsize=11)
    data = document.tobytes()
    document.close()
    return data


def _value(row: dict, *words: str):
    """The value of the one key whose name contains every word; the model names the keys."""
    keys = [key for key in row if all(word in key.lower() for word in words)]
    _expect(len(keys) == 1, f"expected one field named like {'_'.join(words)}, got {sorted(row)}")
    return row[keys[0]]


def check_health(client) -> str:
    body = _json(client.get("/health"), "GET /health")
    _expect(body.get("status") == "ok", f"status is {body.get('status')!r}")
    return "ok"


def check_parse_pdf(client) -> str:
    """Parser: a PDF's text layer comes back (no model call)."""
    response = client.post(
        "/parse",
        files={"file": ("order.pdf", _pdf(PURCHASE_ORDER), "application/pdf")},
        data={"parser_type": "pymupdf"},
    )
    body = _json(response, "POST /parse")
    _expect("PO-7741" in json.dumps(body), "the parsed text does not contain PO-7741")
    return "text layer read"


def check_schema_generator(client) -> str:
    """Schema Generator: three requested fields give a three-field schema."""
    body = _json(
        client.post("/schema-generator", json={"user_requirements": EXTRACTION_TASK}),
        "POST /schema-generator",
    )
    _expect(body["field_count"] == 3, f"field_count is {body['field_count']}, expected 3")
    _expect("delivery" in body["schema_code"], "schema_code has no delivery field")
    return f"{body['field_count']} fields, model {body['model']}"


def check_extract(client) -> str:
    """Extractor: a schema from the task, then values, an ISO date and a requested format."""
    schema = _json(
        client.post("/extract/generate-schema", json={"user_requirements": EXTRACTION_TASK}),
        "POST /extract/generate-schema",
    )
    _expect(len(schema["fields"]) == 3, f"the schema has {len(schema['fields'])} fields, not 3")
    body = _json(
        client.post(
            "/extract/plain-language",
            json={
                "documents": [PURCHASE_ORDER],
                "user_requirements": EXTRACTION_TASK,
                "schema_id": schema["schema_id"],
            },
        ),
        "POST /extract/plain-language",
    )
    _expect(body["document_count"] == 1 and len(body["results"]) == 1, "expected one result")
    row = body["results"][0]
    po_number = _value(row, "po")
    delivery = _value(row, "delivery")
    order = _value(row, "order", "date")
    _expect(po_number == "PO-7741", f"po_number is {po_number!r}")
    _expect(delivery == "10/08/2026", f"delivery_date is {delivery!r}, expected '10/08/2026'")
    _expect(order == "2026-08-02", f"order_date is {order!r}, expected '2026-08-02'")
    return "3 values, requested date format kept"


def check_classify(client) -> str:
    """Document Classifier: an invoice is classified as an invoice."""
    response = client.post(
        "/classify",
        files={"file": ("document.pdf", _pdf(INVOICE), "application/pdf")},
        data={"classes": "invoice,contract,report", "parser": "pymupdf"},
    )
    body = _json(response, "POST /classify")
    _expect(body["classification"] == "invoice", f"classification is {body['classification']!r}")
    return f"invoice, confidence {body['confidence']}"


def check_llm_judge(client) -> str:
    """LLM Judge: the same date in two notations is equivalent, two dates are not."""
    same = _json(
        client.post(
            "/llm-judge/text-pair",
            json={
                "extracted_text": "10 August 2026",
                "expected_text": "2026-08-10",
                "field_name": "delivery_date",
            },
        ),
        "POST /llm-judge/text-pair",
    )
    _expect(same["equivalent"] is True, "the same date in two notations was judged different")
    different = _json(
        client.post(
            "/llm-judge/text-pair",
            json={
                "extracted_text": "10 August 2026",
                "expected_text": "2026-09-12",
                "field_name": "delivery_date",
            },
        ),
        "POST /llm-judge/text-pair",
    )
    _expect(different["equivalent"] is False, "two different dates were judged equivalent")
    return "equivalent and different pairs told apart"


def check_tabular_agent(client) -> str:
    """Tabular Agent: a CSV is loaded and a question about it is answered from the data."""
    upload = _json(
        client.post(
            "/tabular-agent/upload",
            files={"file": ("order_lines.csv", io.BytesIO(ORDER_LINES_CSV.encode()), "text/csv")},
        ),
        "POST /tabular-agent/upload",
    )
    session_id = upload["session_id"]
    try:
        answer = _json(
            client.post(
                "/tabular-agent/ask",
                json={"session_id": session_id, "question": "What is the total quantity?"},
            ),
            "POST /tabular-agent/ask",
        )
        _expect(answer["succeeded"] is True, f"the question failed: {answer.get('error')}"[:160])
        evidence = json.dumps(answer["rows"]) + " " + answer["answer"]
        _expect("42" in evidence, "the answer does not contain the total, 42")
    finally:
        client.delete(f"/tabular-agent/session/{session_id}")
    return "total quantity 42"


CHECKS: dict[str, Callable] = {
    "health": check_health,
    "parse_pdf": check_parse_pdf,
    "schema_generator": check_schema_generator,
    "extract": check_extract,
    "classify": check_classify,
    "llm_judge": check_llm_judge,
    "tabular_agent": check_tabular_agent,
}


def run_checks(client, names: list[str], attempts: int = ATTEMPTS) -> list[dict]:
    """Run the named checks in order and return one report entry per check."""
    report = []
    for name in names:
        entry: dict = {"check": name, "ok": False, "attempts": 0}
        started = time.monotonic()
        for attempt in range(1, attempts + 1):
            entry["attempts"] = attempt
            try:
                entry["detail"] = CHECKS[name](client)
                entry["ok"] = True
                break
            except AssertionError as error:
                entry["detail"] = str(error)[:200]
            except Exception as error:  # noqa: BLE001 - a crash is a failed check, not a crash
                # The message may quote a provider reply; the type is enough to find it.
                entry["detail"] = f"{type(error).__name__} raised"
        entry["seconds"] = round(time.monotonic() - started, 1)
        report.append(entry)
    return report


def format_report(report: list[dict]) -> str:
    lines = []
    for entry in report:
        status = "PASS" if entry["ok"] else "FAIL"
        retried = f" (attempt {entry['attempts']})" if entry["attempts"] > 1 else ""
        lines.append(
            f"{status}  {entry['check']:<18} {entry['seconds']:>6.1f}s  {entry['detail']}{retried}"
        )
    failed = [entry["check"] for entry in report if not entry["ok"]]
    lines.append(
        f"{len(report) - len(failed)} of {len(report)} checks passed"
        + (f"; failed: {', '.join(failed)}" if failed else "")
    )
    return "\n".join(lines)


def _load_app():
    """The API image runs from api/ (``main``); a checkout runs from toolkit_demo_app/."""
    try:
        from main import app
    except ImportError:
        from api.main import app
    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live smoke test of the demo API's use cases.")
    parser.add_argument("--list", action="store_true", help="print the check names and exit")
    parser.add_argument("--only", default="", help="comma-separated check names to run")
    parser.add_argument("--json", dest="json_path", help="write the report to this file")
    args = parser.parse_args(argv)

    if args.list:
        print("\n".join(CHECKS))
        return 0
    names = [name.strip() for name in args.only.split(",") if name.strip()] or list(CHECKS)
    unknown = [name for name in names if name not in CHECKS]
    if unknown:
        print(f"Unknown checks: {', '.join(unknown)}. Known: {', '.join(CHECKS)}")
        return 2

    from fastapi.testclient import TestClient

    with TestClient(_load_app()) as client:
        report = run_checks(client, names)
    print(format_report(report))
    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
    return 0 if all(entry["ok"] for entry in report) else 1


if __name__ == "__main__":
    sys.exit(main())
