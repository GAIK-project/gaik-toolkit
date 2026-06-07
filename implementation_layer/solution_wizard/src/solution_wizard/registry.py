"""Component registry loader and lookup.

The registry is the single source of truth for what GAIK components exist.
Adding a new component means adding one entry to gaik_component_registry.json.
No scoring tables or selection rules are needed here -- the LLM reads the
registry fields (input_artifact_types, output_artifact_types, best_for,
known_limitations) and reasons from them directly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


REGISTRY_PATH = (
    Path(__file__).parent.parent.parent / "registries" / "gaik_component_registry.json"
)
REFERENCE_CARDS_PATH = (
    Path(__file__).parent.parent.parent / "registries" / "component_reference_cards.json"
)

# Required keys per entry, mirroring schemas/component_registry.schema.json.
# Validated on load so a malformed registry fails fast with a clear message
# rather than surfacing as a confusing KeyError later.
_REQUIRED_ENTRY_KEYS = (
    "id",
    "name",
    "type",
    "input_artifact_types",
    "output_artifact_types",
    "required_parameters",
    "best_for",
    "known_limitations",
    "import_path",
    "source_path",
    "readme_path",
    "example_script_path",
)
_VALID_TYPES = ("software_module", "software_component")


def _validate_entries(entries: List[Dict[str, Any]]) -> None:
    if not isinstance(entries, list):
        raise ValueError("Component registry must be a JSON array of entries.")
    seen_ids = set()
    for i, entry in enumerate(entries):
        label = entry.get("name") or entry.get("id") or f"entry #{i}"
        missing = [k for k in _REQUIRED_ENTRY_KEYS if k not in entry]
        if missing:
            raise ValueError(
                f"Registry entry '{label}' is missing required keys: {missing}"
            )
        if entry["type"] not in _VALID_TYPES:
            raise ValueError(
                f"Registry entry '{label}' has invalid type '{entry['type']}' "
                f"(must be one of {_VALID_TYPES})."
            )
        if entry["id"] in seen_ids:
            raise ValueError(f"Duplicate registry id '{entry['id']}'.")
        seen_ids.add(entry["id"])


class Registry:
    def __init__(self, registry_path: Path = REGISTRY_PATH) -> None:
        self._entries: List[Dict[str, Any]] = json.loads(
            registry_path.read_text(encoding="utf-8")
        )
        _validate_entries(self._entries)
        self._by_id: Dict[str, Dict[str, Any]] = {e["id"]: e for e in self._entries}
        self._by_name: Dict[str, Dict[str, Any]] = {e["name"]: e for e in self._entries}

    def all(self) -> List[Dict[str, Any]]:
        return list(self._entries)

    def lookup_by_id(self, component_id: str) -> Optional[Dict[str, Any]]:
        return self._by_id.get(component_id)

    def lookup_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        return self._by_name.get(name)

    def exists(self, id_or_name: str) -> bool:
        return id_or_name in self._by_id or id_or_name in self._by_name

    def filter_by_input_type(self, artifact_type: str) -> List[Dict[str, Any]]:
        return [
            e for e in self._entries
            if artifact_type in e.get("input_artifact_types", [])
        ]

    def filter_by_output_type(self, artifact_type: str) -> List[Dict[str, Any]]:
        return [
            e for e in self._entries
            if artifact_type in e.get("output_artifact_types", [])
        ]

    def modules(self) -> List[Dict[str, Any]]:
        return [e for e in self._entries if e.get("type") == "software_module"]

    def components(self) -> List[Dict[str, Any]]:
        return [e for e in self._entries if e.get("type") == "software_component"]

    def pip_requirements(self, component_names: list) -> list:
        """Return deduplicated gaik[extra] requirement lines for a set of component names.

        Falls back to the reference cards' install_extra for components that are
        wireable in custom pipelines but not in the curated registry (e.g. parsers).
        """
        cards = None
        extras = set()
        for name in component_names:
            entry = self.lookup_by_id(name) or self.lookup_by_name(name)
            if entry and entry.get("install_extra"):
                extras.add(entry["install_extra"])
                continue
            # Card fallback for non-registry building blocks
            if cards is None:
                try:
                    cards = get_reference_cards()
                except Exception:
                    cards = False
            if cards:
                card = cards.get(name)
                if card and card.get("install_extra"):
                    extras.add(card["install_extra"])
        lines = ["pydantic>=2", "python-dotenv"]
        for extra in sorted(extras):
            lines.append(f"gaik[{extra}]")
        return lines

    def as_llm_context(self) -> str:
        """Return a compact registry summary suitable for inclusion in a prompt."""
        lines = []
        for e in self._entries:
            lines.append(
                f"- {e['name']} ({e['type']})"
                f"\n    inputs:  {e['input_artifact_types']}"
                f"\n    outputs: {e['output_artifact_types']}"
                f"\n    best_for: {e.get('best_for', [])}"
                f"\n    limitations: {e.get('known_limitations', [])}"
            )
        return "\n".join(lines)


class ReferenceCards:
    """Call-pattern cards for wiring components in custom (_generic) pipelines.

    Each card holds the verified import line, constructor pattern, main-method
    call, return shape, and pip extra for one component or module. The cards are
    injected into the generic PoC skeleton so the agent does not have to guess
    component API signatures (the #1 runtime failure mode).
    """

    _REQUIRED_CARD_KEYS = ("import", "construct", "call", "returns")

    def __init__(self, cards_path: Path = REFERENCE_CARDS_PATH) -> None:
        self._cards: Dict[str, Dict[str, str]] = json.loads(
            cards_path.read_text(encoding="utf-8")
        )
        self._validate()

    def _validate(self) -> None:
        for name, card in self._cards.items():
            missing = [k for k in self._REQUIRED_CARD_KEYS if k not in card]
            if missing:
                raise ValueError(
                    f"Reference card '{name}' is missing required keys: {missing}"
                )

    def get(self, component_name: str) -> Optional[Dict[str, str]]:
        return self._cards.get(component_name)

    def names(self) -> List[str]:
        return list(self._cards.keys())


_registry: Optional[Registry] = None
_reference_cards: Optional[ReferenceCards] = None


def get_registry() -> Registry:
    global _registry
    if _registry is None:
        _registry = Registry()
    return _registry


def get_reference_cards() -> ReferenceCards:
    global _reference_cards
    if _reference_cards is None:
        _reference_cards = ReferenceCards()
    return _reference_cards
