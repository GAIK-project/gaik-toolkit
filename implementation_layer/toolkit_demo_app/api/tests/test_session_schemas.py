"""Session schemas: generated once for a prompt, reused until the prompt changes."""

import asyncio

import pytest
from api.routers import pipeline
from api.utils import session_schemas
from fastapi import HTTPException
from pydantic import BaseModel, Field


class Incident(BaseModel):
    place: str | None = Field(default=None, description="Where it happened")


PROMPT = "Extract the incident: place and people involved."


def test_a_stored_schema_is_found_for_the_same_prompt():
    schema_id = session_schemas.store_session_schema(PROMPT, Incident, object())

    # Trailing spaces and surrounding blank lines do not make a different prompt.
    found = session_schemas.find_session_schema(schema_id, f"\n{PROMPT}  \n")

    assert found.schema is Incident


def test_a_changed_prompt_needs_a_new_schema():
    schema_id = session_schemas.store_session_schema(PROMPT, Incident, object())

    with pytest.raises(ValueError, match="changed"):
        session_schemas.find_session_schema(schema_id, PROMPT + " Also the cause.")


def test_an_unknown_id_is_reported():
    with pytest.raises(ValueError, match="no longer available"):
        session_schemas.find_session_schema("missing", PROMPT)


def test_the_oldest_schemas_are_dropped():
    first = session_schemas.store_session_schema("first prompt text", Incident, object())
    for index in range(session_schemas.SESSION_SCHEMA_LIMIT):
        session_schemas.store_session_schema(f"prompt number {index} text", Incident, object())

    with pytest.raises(ValueError):
        session_schemas.find_session_schema(first, "first prompt text")


def test_long_schema_names_are_shortened():
    model = type("x" * 80, (BaseModel,), {})

    assert len(session_schemas.shorten_schema_name(model).__name__) <= 60


def _fake_generator(monkeypatch):
    class Generator:
        def __init__(self, **_):
            self.item_requirements = object()

        def generate_schema(self, prompt):
            return Incident

    monkeypatch.setattr("gaik.software_components.extractor.schema.SchemaGenerator", Generator)
    monkeypatch.setattr(pipeline, "get_api_config", lambda: {"model": "m"})
    monkeypatch.setattr(pipeline, "get_model_options", lambda config: {})


def test_the_schema_endpoint_returns_an_id_and_the_fields(monkeypatch):
    _fake_generator(monkeypatch)

    body = asyncio.run(pipeline.generate_session_schema(PROMPT))

    assert [field["name"] for field in body["fields"]] == ["place"]
    entry = session_schemas.find_session_schema(body["schema_id"], PROMPT)
    assert entry.schema.__name__.startswith("Incident")


@pytest.mark.parametrize("prompt", ["", "short", "x" * (pipeline.MAX_SCHEMA_PROMPT_CHARS + 1)])
def test_the_schema_endpoint_rejects_empty_and_oversized_prompts(prompt):
    with pytest.raises(HTTPException) as error:
        asyncio.run(pipeline.generate_session_schema(prompt))

    assert error.value.status_code == 400


def test_the_pipeline_uses_the_session_schema_without_generating(monkeypatch):
    schema_id = session_schemas.store_session_schema(PROMPT, Incident, "requirements")

    schema, requirements, generated = pipeline._get_or_create_schema(
        config={},
        user_requirements=PROMPT,
        schema_key=None,
        regenerate_schema=True,
        schema_id=schema_id,
    )

    assert (schema, requirements, generated) == (Incident, "requirements", False)
