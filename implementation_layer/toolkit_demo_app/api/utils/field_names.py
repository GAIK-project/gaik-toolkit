"""Give generated field names back the letters of the language they were written in.

The schema generator turns every character outside a-z and 0-9 into an underscore, so
``päivämäärä`` arrives as ``p_iv_m_r`` and ``tehdyt välittömät toimenpiteet`` as
``tehdyt_v_litt_m_t_toimenpiteet``. The generator is left as it is. Here the names are
matched against the words of the prompt and of the field descriptions, and the original
spelling is put back in what the user sees: the schema listing, the extracted data and
the report.
"""

import re
import unicodedata
from typing import Any, get_args

from pydantic import BaseModel

MAX_PHRASE_WORDS = 8
_SPLIT = re.compile(r"[.\n:;,()!?/|•]+")
_WORD = re.compile(r"\w+")


def _generator_name(text: str) -> str:
    """What the schema generator makes of a phrase."""
    return re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()


def _ascii_name(text: str) -> str:
    """The phrase with accents removed: ``päivämäärä`` -> ``paivamaara``."""
    plain = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    return _generator_name(plain)


def _snake(words: list[str]) -> str:
    return "_".join(word.lower() for word in words)


def restore_field_names(names: set[str], texts: list[str]) -> dict[str, str]:
    """Map generated names to their original spelling, when a phrase in *texts* gives it.

    A name is restored from a phrase when the generator would have produced exactly that
    name from the phrase, or when the name is the phrase without its accents.
    """
    wanted = {name for name in names if name}
    found: dict[str, str] = {}
    for text in texts:
        for segment in _SPLIT.split(text or ""):
            words = _WORD.findall(segment)
            for start in range(len(words)):
                for size in range(1, MAX_PHRASE_WORDS + 1):
                    phrase = words[start : start + size]
                    if len(phrase) < size:
                        break
                    restored = _snake(phrase)
                    if restored.isascii():
                        continue
                    for key in (_generator_name(restored), _ascii_name(restored)):
                        if key in wanted and key not in found:
                            found[key] = restored
    return found


def _child_models(annotation: Any) -> list[type[BaseModel]]:
    found = []
    for arg in get_args(annotation):
        if isinstance(arg, type) and issubclass(arg, BaseModel):
            found.append(arg)
        else:
            found.extend(_child_models(arg))
    return found


def schema_names_and_descriptions(schema: type[BaseModel]) -> tuple[set[str], list[str]]:
    """Every field name of the schema, with those of nested records, and the descriptions."""
    names: set[str] = set()
    descriptions: list[str] = []
    for name, info in schema.model_fields.items():
        names.add(name)
        if info.description:
            descriptions.append(info.description)
        for child in _child_models(info.annotation):
            child_names, child_descriptions = schema_names_and_descriptions(child)
            names |= child_names
            descriptions += child_descriptions
    return names, descriptions


def field_name_mapping(schema: type[BaseModel], user_requirements: str) -> dict[str, str]:
    names, descriptions = schema_names_and_descriptions(schema)
    return restore_field_names(names, [user_requirements, *descriptions])


def rename_keys(data: Any, mapping: dict[str, str]) -> Any:
    """The data with its keys renamed, at every depth. A rename never overwrites a key."""
    if not mapping:
        return data
    if isinstance(data, list):
        return [rename_keys(item, mapping) for item in data]
    if isinstance(data, dict):
        renamed: dict[Any, Any] = {}
        for key, value in data.items():
            target = mapping.get(key, key) if isinstance(key, str) else key
            if target != key and (target in data or target in renamed):
                target = key
            renamed[target] = rename_keys(value, mapping)
        return renamed
    return data


def rename_described_fields(fields: list[dict], mapping: dict[str, str]) -> list[dict]:
    """The schema listing (name, type, description, children) with restored names."""
    if not mapping:
        return fields
    return [
        {
            **field,
            "name": mapping.get(field["name"], field["name"]),
            **(
                {"children": rename_described_fields(field["children"], mapping)}
                if field.get("children")
                else {}
            ),
        }
        for field in fields
    ]
