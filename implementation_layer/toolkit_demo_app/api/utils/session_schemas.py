"""Schemas generated for one demo session: kept in memory, never saved to disk."""

import uuid
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

SESSION_SCHEMA_LIMIT = 32

# Names longer than this are rejected by OpenAI's structured output; the generator names
# the model after the start of the prompt.
MAX_SCHEMA_NAME = 60


@dataclass(frozen=True)
class SessionSchema:
    user_requirements: str
    schema: Any
    requirements: Any


_schemas: OrderedDict[str, SessionSchema] = OrderedDict()


def normalize_prompt(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


def shorten_schema_name(schema: Any) -> Any:
    if len(schema.__name__) > MAX_SCHEMA_NAME:
        schema.__name__ = schema.__name__[:MAX_SCHEMA_NAME].rstrip("_")
        schema.__qualname__ = schema.__name__
    return schema


def store_session_schema(user_requirements: str, schema: Any, requirements: Any) -> str:
    schema_id = uuid.uuid4().hex
    _schemas[schema_id] = SessionSchema(normalize_prompt(user_requirements), schema, requirements)
    _schemas.move_to_end(schema_id)
    while len(_schemas) > SESSION_SCHEMA_LIMIT:
        _schemas.popitem(last=False)
    return schema_id


def find_session_schema(schema_id: str, user_requirements: str) -> SessionSchema:
    """The schema made for exactly this prompt; raises ValueError when it is gone or stale."""
    entry = _schemas.get(schema_id)
    if entry is None:
        raise ValueError("The schema is no longer available. Generate it again.")
    if entry.user_requirements != normalize_prompt(user_requirements):
        raise ValueError("The prompt changed after the schema was generated. Generate it again.")
    _schemas.move_to_end(schema_id)
    return entry
