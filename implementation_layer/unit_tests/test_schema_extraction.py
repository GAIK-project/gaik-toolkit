"""End-to-end extraction test — schema generation + data extraction with a real LLM.

Needs Azure OpenAI: ``AZURE_API_KEY`` and ``AZURE_ENDPOINT``, with ``AZURE_DEPLOYMENT``
naming the chat deployment. Skipped when the key or the endpoint is missing.
"""

import json
import os
import re

import pytest
from gaik.software_components.config import get_openai_config
from gaik.software_components.extractor.extractor import DataExtractor
from gaik.software_components.extractor.schema import (
    create_extraction_model,
    parse_user_requirements,
    print_pydantic_schema,
)

_MISSING = [name for name in ("AZURE_API_KEY", "AZURE_ENDPOINT") if not os.getenv(name, "").strip()]

# Calls a real LLM: these assert on model output, so they fail when the model or
# the Azure deployment changes, not only when our code regresses. Kept out of the
# push gate (`-m "not llm"`); see .github/workflows/test.yml.
pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(bool(_MISSING), reason=f"live Azure OpenAI test: set {', '.join(_MISSING)}"),
]


EXTRACTION_TASK = """
Extract the following fields from an incident report.

RULES:
- Extract only explicitly stated information.
- If information is not mentioned, return empty string "".
- Never use null or None.

FIELDS:

- Report type
  One of: "safety", "environmental", "energy".
  If unclear, default to "safety".

- Observer name
  Full name of the person who made the observation. If not mentioned, return "".

- Date
  The date of the incident. Format: DD.MM.YYYY.
  If not mentioned, return "".

- Time
  The time of the incident, as written in the source. If not mentioned, return "".

- Location
  Where the event took place. If not mentioned, return "".

- Description
  One sentence summary of what happened (max 12 words). If not described, return "".

- Near miss
  One of: "Yes", "No".
  Return "Yes" if a near miss or injury is mentioned. Otherwise "No".

- Actions taken
  Any corrective actions already taken. If not mentioned, return "".

- Suggestion
  Any future improvement suggested. If not mentioned, return "".
"""

EXTRACTION_DOCUMENT = """
Moi, 25.8.2025 Vetamon kieppipeittauksessa huomasin, etta karsatrukin karsasta
puuttuu pultti ja alatuki oli irti. Karsa pitaa korjata, ilmoitin asiasta eteenpain.
"""


# One keyword per field of the task. The model names the fields, so a name is matched
# by keyword ("observer_name" or "observer"), not exactly.
FIELD_KEYWORDS = [
    "type",
    "observer",
    "date",
    "time",
    "location",
    "description",
    "near",
    "action",
    "suggest",
]


def _field_name(requirements, keyword: str) -> str:
    names = [f.field_name for f in requirements.fields]
    matches = [name for name in names if keyword in name]
    assert matches, f"no field name contains {keyword!r}: {names}"
    return matches[0]


def test_extraction():
    """Parse requirements, generate schema, extract data from an incident report."""
    requirements = parse_user_requirements(EXTRACTION_TASK)
    names = [f.field_name for f in requirements.fields]
    assert len(names) == len(FIELD_KEYWORDS), names
    for keyword in FIELD_KEYWORDS:
        _field_name(requirements, keyword)

    model = create_extraction_model(requirements)
    print_pydantic_schema(model, title="Incident Report — Generated Model")

    extractor = DataExtractor(config=get_openai_config(use_azure=True))
    results = extractor.extract(
        extraction_model=model,
        requirements=requirements,
        user_requirements=EXTRACTION_TASK,
        documents=[EXTRACTION_DOCUMENT],
    )
    print(json.dumps(results, indent=2, default=str, ensure_ascii=False))

    assert len(results) == 1
    result = results[0]
    # Every field is present, and every value has its field's type (enums included).
    assert set(result) == set(names)
    model.model_validate(result)

    # Facts the document states plainly. The date is 25.8.2025, in whatever format.
    date = result[_field_name(requirements, "date")]
    assert {int(n) for n in re.findall(r"\d+", date)} == {25, 8, 2025}, date
    location = result[_field_name(requirements, "location")].lower()
    assert "vetamo" in location or "kieppipeitt" in location, location
    # A missing bolt on a forklift is a safety observation, also the task's default.
    assert result[_field_name(requirements, "type")].lower() == "safety"


if __name__ == "__main__":
    test_extraction()
