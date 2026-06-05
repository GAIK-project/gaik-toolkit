"""Integration test — calls parse_user_requirements() with a real LLM.

Requires a valid API key (Azure OpenAI or OpenAI) in the environment.
"""

from gaik.software_components.extractor.schema import (
    create_extraction_model,
    parse_user_requirements,
    print_pydantic_schema,
)

FINNISH_INCIDENT_TASK = r"""
TASK:
Extract the following fields from a job posting.

RULES:
- Extract only explicitly stated information.
- Do not infer salary from job title or seniority.
- Numeric fields should be null if not mentioned.
- Boolean fields should be true/false based on what is stated.

FIELDS:

- Job title
  The exact title of the position as written in the posting. Required.

- Company name
  The hiring organization. Required.

- Location
  City and/or country. If the posting says "remote only" with no location, return "Remote".

- Employment type
  One of: "full-time" / "part-time" / "contract" / "internship".
  If not specified, default to "full-time".

- Department
  One of: "Engineering", "Marketing", "Sales", "HR", "Finance", "Operations", "Design", "Legal".
  If not clearly stated, return "".

- Minimum salary
  Lower bound of salary range in EUR. A precise monetary value.
  If no salary is mentioned, this should be null.

- Maximum salary
  Upper bound of salary range in EUR. A precise monetary value.
  If no salary is mentioned, this should be null.

- Experience required (years)
  Minimum years of experience. A whole number.
  If not mentioned, this should be null.

- Remote work allowed
  true if the posting mentions remote or hybrid options. false otherwise.

- Posted date
  The date when the job was posted. Format: DD/MM/YYYY.

- Required skills
  A list of required skills, technologies, or qualifications mentioned.

- Visa sponsorship available
  One of: "yes" / "no".
  If not mentioned, default to "no".

- Job description summary
  A one-paragraph summary of the role. Required.
"""


def test_finnish_incident_report_schema():
    """Parse the Finnish incident report task and verify the generated model."""
    print("\n" + "=" * 80)
    print("STEP 1: parse_user_requirements()")
    print("=" * 80)
    requirements = parse_user_requirements(FINNISH_INCIDENT_TASK)

    print(f"\nuse_case_name: {requirements.use_case_name}")
    print(f"field count:   {len(requirements.fields)}")
    print()

    for f in requirements.fields:
        print(
            f"  {f.field_name:40s} type={f.field_type:10s} "
            f"nullable={f.nullable!s:5s} "
            f"has_default={f.has_explicit_default!s:5s} "
            f"default={f.default!r:20s} "
            f"enum={f.enum}"
        )

    print("\n" + "=" * 80)
    print("STEP 2: create_extraction_model()")
    print("=" * 80)
    model = create_extraction_model(requirements)
    print_pydantic_schema(model, title="Finnish Incident Report — Generated Model")

    _print_field_details(model)

    assert len(model.model_fields) == 13, f"Expected 13 fields, got {len(model.model_fields)}"


def _print_field_details(model):
    from pydantic_core import PydanticUndefined

    print("\nField details:")
    print("-" * 100)
    for name, info in model.model_fields.items():
        ann = info.annotation
        req = info.is_required()
        default = info.default
        if default is PydanticUndefined and info.default_factory is not None:
            default = info.default_factory()
        print(f"  {name:40s} required={req!s:5s}  default={default!r:25s}  type={ann}")


if __name__ == "__main__":
    test_finnish_incident_report_schema()
