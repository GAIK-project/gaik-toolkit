"""End-to-end date extraction tests — verifies date format handling.

Two scenarios:
  A) User specifies an output format (e.g., "DD/MM/YYYY") → date is formatted accordingly
  B) No format specified → date is normalized to ISO (YYYY-MM-DD)

Requires a valid API key (Azure OpenAI or OpenAI) in the environment.
"""

import json

import pytest

from gaik.software_components.config import get_openai_config
from gaik.software_components.extractor.extractor import DataExtractor
from gaik.software_components.extractor.schema import (
    create_extraction_model,
    parse_user_requirements,
    print_pydantic_schema,
)

# ===================================================================
# A) USER SPECIFIES OUTPUT FORMAT — date should match that format
# ===================================================================

# ---------------------------------------------------------------------------
# A1: Format DD/MM/YYYY — European slash
# ---------------------------------------------------------------------------

# Calls a real LLM: these assert on model output, so they fail when the model or
# the Azure deployment changes, not only when our code regresses. Kept out of the
# push gate (`-m "not llm"`); see .github/workflows/test.yml.
pytestmark = pytest.mark.llm


TASK_FORMAT_DD_SLASH_MM_SLASH_YYYY = """
Extract the following fields from an incident report.

RULES:
- Extract only explicitly stated information.
- If information is not mentioned, return "".

FIELDS:

- Incident date
  The date of the incident. Format: DD/MM/YYYY.
  If not mentioned, return "".

- Reporter
  Name of the person who reported. If not mentioned, return "".

- Description
  Brief summary of what happened. If not mentioned, return "".
"""

DOC_A1 = """
On March 15, 2024, engineer Maria Lopez reported a gas leak in Section C.
The area was evacuated and the leak was sealed within two hours.
"""

EXPECTED_A1 = {
    "date_field": "incident_date",
    "date_value": "15/03/2024",
    "reporter": "Maria Lopez",
}

# ---------------------------------------------------------------------------
# A2: Format DD.MM.YYYY — European dot
# ---------------------------------------------------------------------------

TASK_FORMAT_DD_DOT_MM_DOT_YYYY = """
Extract the following fields from a safety observation.

RULES:
- Extract only explicitly stated information.
- If information is not mentioned, return "".

FIELDS:

- Observation date
  The date of the observation. Format: DD.MM.YYYY.
  If not mentioned, return "".

- Observer
  Name of the observer. If not mentioned, return "".

- Location
  Where the observation was made. If not mentioned, return "".
"""

DOC_A2 = """
Safety observation by Jukka Virtanen on 2024-08-15 at the warehouse loading dock.
A forklift was found operating without its warning beacon active.
"""

EXPECTED_A2 = {
    "date_field": "observation_date",
    "date_value": "15.08.2024",
    "observer": "Jukka Virtanen",
}

# ---------------------------------------------------------------------------
# A3: Format YYYY-MM-DD — ISO explicit
# ---------------------------------------------------------------------------

TASK_FORMAT_YYYY_MM_DD = """
Extract the following fields from an audit log.

RULES:
- Extract only explicitly stated information.
- If information is not mentioned, return "".

FIELDS:

- Audit date
  The date of the audit. Format: YYYY-MM-DD.
  If not mentioned, return "".

- Auditor
  Name of the auditor. If not mentioned, return "".

- Finding
  Main finding of the audit. If not mentioned, return "".
"""

DOC_A3 = """
Internal audit conducted by Anna Kowalski on 23/11/2024.
Finding: Emergency exits on floor 3 were partially blocked by stored materials.
"""

EXPECTED_A3 = {
    "date_field": "audit_date",
    "date_value": "2024-11-23",
    "auditor": "Anna Kowalski",
}

# ---------------------------------------------------------------------------
# A4: Format MM/DD/YYYY — US format
# ---------------------------------------------------------------------------

TASK_FORMAT_MM_SLASH_DD_SLASH_YYYY = """
Extract the following fields from a work order.

RULES:
- Extract only explicitly stated information.
- If information is not mentioned, return "".

FIELDS:

- Work order date
  The date of the work order. Format: MM/DD/YYYY.
  If not mentioned, return "".

- Technician
  Name of the assigned technician. If not mentioned, return "".

- Task
  Description of the work to be done. If not mentioned, return "".
"""

DOC_A4 = """
Work Order #WO-2024-445
Issued on 22.05.2024.
Assigned to: Robert Chen
Task: Replace faulty pressure valve on boiler unit 3.
"""

EXPECTED_A4 = {
    "date_field": "work_order_date",
    "date_value": "05/22/2024",
    "technician": "Robert Chen",
}


# ===================================================================
# B) NO FORMAT SPECIFIED — date should normalize to ISO (YYYY-MM-DD)
# ===================================================================

# ---------------------------------------------------------------------------
# B1: European dot date, no format in task → ISO
# ---------------------------------------------------------------------------

TASK_NO_FORMAT_EU_DOT = """
Extract the following fields from a maintenance log.

RULES:
- Extract only explicitly stated information.
- If information is not mentioned, return "".

FIELDS:

- Date
  The date of the maintenance event.
  If not mentioned, return "".

- Technician
  Name of the technician. If not mentioned, return "".

- Equipment
  Name or ID of the equipment serviced. If not mentioned, return "".
"""

DOC_B1 = """
Maintenance log entry: On 18.09.2024, technician Pekka Hämäläinen
serviced compressor unit CP-12. All filters were replaced.
"""

EXPECTED_B1 = {
    "date_field": "date",
    "date_value": "2024-09-18",
    "technician": "Pekka Hämäläinen",
}

# ---------------------------------------------------------------------------
# B2: Written-out English date, no format → ISO
# ---------------------------------------------------------------------------

TASK_NO_FORMAT_WRITTEN = """
Extract the following fields from an event report.

RULES:
- Extract only explicitly stated information.
- If information is not mentioned, return "".

FIELDS:

- Event date
  The date the event occurred.
  If not mentioned, return "".

- Reported by
  Name of the reporter. If not mentioned, return "".

- Summary
  Brief description. If not mentioned, return "".
"""

DOC_B2 = """
Event Report by Sarah Williams.
On June 3, 2024, a power outage affected the east wing of the data center
for approximately 45 minutes.
"""

EXPECTED_B2 = {
    "date_field": "event_date",
    "date_value": "2024-06-03",
    "reported_by": "Sarah Williams",
}

# ---------------------------------------------------------------------------
# B3: Slash date, no format → ISO
# ---------------------------------------------------------------------------

TASK_NO_FORMAT_SLASH = """
Extract the following fields from a delivery receipt.

RULES:
- Extract only explicitly stated information.
- If information is not mentioned, return "".

FIELDS:

- Delivery date
  The date of the delivery.
  If not mentioned, return "".

- Receiver
  Name of the person who received the delivery. If not mentioned, return "".

- Item count
  Number of items. An integer. If not mentioned, return null.
"""

DOC_B3 = """
Delivery receipt: 25/12/2024
Received by: Henrik Johansson
Items: 120 units of insulation panels (SKU-8841)
"""

EXPECTED_B3 = {
    "date_field": "delivery_date",
    "date_value": "2024-12-25",
    "receiver": "Henrik Johansson",
}

# ---------------------------------------------------------------------------
# B4: No date in document, no format → empty string
# ---------------------------------------------------------------------------

TASK_NO_FORMAT_MISSING = """
Extract the following fields from a meeting note.

RULES:
- Extract only explicitly stated information.
- If information is not mentioned, return "".

FIELDS:

- Meeting date
  The date of the meeting.
  If no date is mentioned, return "".

- Chairperson
  Name of the person who chaired the meeting. If not mentioned, return "".

- Decision
  Any decision made. If not mentioned, return "".
"""

DOC_B4 = """
The team met to discuss the migration timeline. Led by David Park.
Decision: postpone the database migration to after the holiday freeze.
"""

EXPECTED_B4 = {
    "date_field": "meeting_date",
    "date_value": "",
    "chairperson": "David Park",
}


# ===================================================================
# Test runner
# ===================================================================

# One test per case, so each fails on its own. A2 and B4 were xfail while the cases
# were one test (May 2026); both pass live on gaik 0.11 (#98), so no case is marked.
FORMAT_CASES = [
    pytest.param(TASK_FORMAT_DD_SLASH_MM_SLASH_YYYY, DOC_A1, EXPECTED_A1, id="A1-dd-mm-yyyy-slash"),
    pytest.param(TASK_FORMAT_DD_DOT_MM_DOT_YYYY, DOC_A2, EXPECTED_A2, id="A2-dd-mm-yyyy-dot"),
    pytest.param(TASK_FORMAT_YYYY_MM_DD, DOC_A3, EXPECTED_A3, id="A3-yyyy-mm-dd"),
    pytest.param(TASK_FORMAT_MM_SLASH_DD_SLASH_YYYY, DOC_A4, EXPECTED_A4, id="A4-mm-dd-yyyy-slash"),
    pytest.param(TASK_NO_FORMAT_EU_DOT, DOC_B1, EXPECTED_B1, id="B1-no-format-eu-dot-to-iso"),
    pytest.param(TASK_NO_FORMAT_WRITTEN, DOC_B2, EXPECTED_B2, id="B2-no-format-written-to-iso"),
    pytest.param(TASK_NO_FORMAT_SLASH, DOC_B3, EXPECTED_B3, id="B3-no-format-slash-to-iso"),
    pytest.param(TASK_NO_FORMAT_MISSING, DOC_B4, EXPECTED_B4, id="B4-no-format-missing-date"),
]


def run_extraction(task: str, document: str, label: str):
    """Run full pipeline: parse → model → extract. Return result dict and requirements."""
    print(f"\n{'=' * 80}")
    print(f"CASE: {label}")
    print("=" * 80)

    print("\n--- parse_user_requirements ---")
    requirements = parse_user_requirements(task)
    print(f"use_case_name: {requirements.use_case_name}")
    print(f"field count:   {len(requirements.fields)}")
    for f in requirements.fields:
        print(
            f"  {f.field_name:30s} type={f.field_type:10s} "
            f"format={f.format!r:20s} "
            f"has_default={f.has_explicit_default!s:5s} "
            f"default={f.default!r}"
        )

    print("\n--- create_extraction_model ---")
    model = create_extraction_model(requirements)
    print_pydantic_schema(model, title=label)

    print("\n--- extract ---")
    config = get_openai_config(use_azure=True)
    extractor = DataExtractor(config=config)
    results = extractor.extract(
        extraction_model=model,
        requirements=requirements,
        user_requirements=task,
        documents=[document],
    )

    assert len(results) == 1
    return results[0]


@pytest.mark.parametrize(("task", "document", "expected"), FORMAT_CASES)
def test_date_format_handling(task, document, expected, request):
    """The date comes out in the task's format, or as ISO without one."""
    label = request.node.callspec.id
    result = run_extraction(task, document, label)
    print("\n--- result ---")
    print(json.dumps(result, indent=2, default=str, ensure_ascii=False))

    date_key = expected["date_field"]
    actual_date = result.get(date_key)
    assert not (isinstance(actual_date, str) and "snake_case" in actual_date.lower()), (
        f"{date_key} = {actual_date!r}: 'snake_case' leaked"
    )

    wanted = {date_key: expected["date_value"]}
    wanted.update((k, v) for k, v in expected.items() if k not in ("date_field", "date_value"))
    assert {key: result.get(key) for key in wanted} == wanted


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-m", "llm", "-s"]))
