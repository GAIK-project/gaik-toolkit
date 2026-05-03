"""End-to-end extraction test — schema generation + data extraction with a real LLM.

Requires a valid API key (Azure OpenAI or OpenAI) in the environment.
"""

import json

from gaik.software_components.config import get_openai_config
from gaik.software_components.extractor.extractor import DataExtractor
from gaik.software_components.extractor.schema import (
    create_extraction_model,
    parse_user_requirements,
    print_pydantic_schema,
)

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


def test_extraction():
    """Parse requirements, generate schema, extract data from an incident report."""
    print("\n" + "=" * 80)
    print("STEP 1: parse_user_requirements()")
    print("=" * 80)
    requirements = parse_user_requirements(EXTRACTION_TASK)

    print(f"\nuse_case_name: {requirements.use_case_name}")
    print(f"field count:   {len(requirements.fields)}")
    print()
    for f in requirements.fields:
        print(
            f"  {f.field_name:30s} type={f.field_type:10s} "
            f"format={f.format!r:15s} "
            f"has_default={f.has_explicit_default!s:5s} "
            f"default={f.default!r:15s} "
            f"enum={f.enum}"
        )

    print("\n" + "=" * 80)
    print("STEP 2: create_extraction_model()")
    print("=" * 80)
    model = create_extraction_model(requirements)
    print_pydantic_schema(model, title="Incident Report — Generated Model")

    print("\n" + "=" * 80)
    print("STEP 3: extract()")
    print("=" * 80)
    config = get_openai_config(use_azure=True)
    extractor = DataExtractor(config=config)
    results = extractor.extract(
        extraction_model=model,
        requirements=requirements,
        user_requirements=EXTRACTION_TASK,
        documents=[EXTRACTION_DOCUMENT],
    )

    print("\n" + "=" * 80)
    print("EXTRACTED DATA (JSON)")
    print("=" * 80)
    print(json.dumps(results, indent=2, default=str, ensure_ascii=False))


if __name__ == "__main__":
    test_extraction()
