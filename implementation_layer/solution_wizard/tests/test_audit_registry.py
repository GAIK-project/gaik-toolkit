"""Tests for gaik-sync internal-package and public-alias exemptions.

The `llm` subpackage (gaik.software_components.llm) is a multi-provider LLM
client abstraction consumed internally by many components -- not a
user-facing component the wizard should ever select directly. Without an
explicit exemption, check_new() would flag it on every run, so `--strict`
audits could never pass cleanly. See INTERNAL_ONLY_SUBPACKAGES in
audit_registry.py.

The `schema_generator` subpackage is a public import alias for the existing
`extractor.SchemaGenerator` component. It must resolve to the same class while
remaining excluded from new-component discovery so the wizard never registers
the same component twice.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = (
    Path(__file__).parents[3] / ".claude" / "skills" / "gaik-sync" / "scripts" / "audit_registry.py"
)


@pytest.fixture(scope="module")
def audit_registry():
    spec = importlib.util.spec_from_file_location("_audit_registry", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_audit_registry"] = module
    spec.loader.exec_module(module)
    return module


def test_llm_subpackage_is_in_the_internal_ignore_list(audit_registry):
    assert "gaik.software_components.llm" in audit_registry.INTERNAL_ONLY_SUBPACKAGES


def test_agentic_report_pipeline_is_in_the_internal_ignore_list(audit_registry):
    """Reached only through MultiSourceReportGenerator(agentic=True), whose card
    documents the option; it has no component identity of its own."""
    nested = "gaik.software_modules.multi_source_report_generator.agentic"

    assert nested in audit_registry.INTERNAL_ONLY_SUBPACKAGES


def test_schema_generator_subpackage_is_in_the_alias_list(audit_registry):
    assert (
        audit_registry.ALIAS_SUBPACKAGES["gaik.software_components.schema_generator"]
        == "gaik.software_components.extractor"
    )


def test_schema_generator_alias_reexports_the_canonical_class():
    extractor = pytest.importorskip("gaik.software_components.extractor")
    schema_generator = pytest.importorskip("gaik.software_components.schema_generator")

    assert schema_generator.SchemaGenerator is extractor.SchemaGenerator


def test_check_new_does_not_flag_an_exempted_subpackage(audit_registry, monkeypatch):
    """check_new() must skip anything listed in INTERNAL_ONLY_SUBPACKAGES,
    regardless of whether any card happens to reference it."""
    monkeypatch.setattr(
        audit_registry,
        "_gaik_subpackages",
        lambda: {"gaik.software_components.llm": "gaik.software_components"},
    )

    class _EmptyCards:
        def names(self):
            return []

        def get(self, name):
            raise KeyError(name)

    findings = audit_registry.check_new(reg=None, cards=_EmptyCards())
    assert findings == []


def test_check_new_does_not_flag_an_alias_subpackage(audit_registry, monkeypatch):
    """A public alias must not become a duplicate wizard component."""
    monkeypatch.setattr(
        audit_registry,
        "_gaik_subpackages",
        lambda: {"gaik.software_components.schema_generator": "gaik.software_components"},
    )

    class _EmptyCards:
        def names(self):
            return []

        def get(self, name):
            raise KeyError(name)

    findings = audit_registry.check_new(reg=None, cards=_EmptyCards())
    assert findings == []


def test_check_new_still_flags_a_genuinely_untracked_subpackage(audit_registry, monkeypatch):
    """The exemption must be specific -- an unrelated untracked subpackage
    should still surface as a 'new' finding."""
    monkeypatch.setattr(
        audit_registry,
        "_gaik_subpackages",
        lambda: {"gaik.software_components.totally_new_thing": "gaik.software_components"},
    )

    class _EmptyCards:
        def names(self):
            return []

        def get(self, name):
            raise KeyError(name)

    findings = audit_registry.check_new(reg=None, cards=_EmptyCards())
    assert len(findings) == 1
    assert findings[0]["category"] == "new"
    assert findings[0]["component"] == "totally_new_thing"


# --- nested packages of a known family ---------------------------------------
#
# check_new() stops at gaik.software_components.RAG: one card importing from RAG
# made the whole family look tracked, so a class in a nested package without a card
# (RAG.vector_store.VectorStore) was never reported. check_new_nested() asks about
# each nested package.


class _Cards:
    """Reference cards with the given import lines, for the check to read."""

    def __init__(self, *imports):
        self._cards = {f"card{i}": {"import": line} for i, line in enumerate(imports)}

    def names(self):
        return list(self._cards)

    def get(self, name):
        return self._cards[name]


_RAG = "gaik.software_components.RAG"
_NESTED = f"{_RAG}.vector_store"


def _only_nested(monkeypatch, audit_registry, *paths, defined_in=()):
    monkeypatch.setattr(
        audit_registry, "_gaik_nested_subpackages", lambda: {p: _RAG for p in paths}
    )
    monkeypatch.setattr(audit_registry, "_card_class_modules", lambda cards: set(defined_in))


def test_check_new_nested_flags_a_nested_package_no_card_covers(audit_registry, monkeypatch):
    _only_nested(monkeypatch, audit_registry, _NESTED)

    findings = audit_registry.check_new_nested(_Cards(f"from {_RAG}.retriever import Retriever"))

    assert [(f["category"], f["component"]) for f in findings] == [("new", "vector_store")]
    assert _NESTED in findings[0]["detail"]


def test_check_new_nested_accepts_a_card_that_imports_from_the_package(audit_registry, monkeypatch):
    _only_nested(monkeypatch, audit_registry, _NESTED)

    cards = _Cards(f"from {_NESTED} import VectorStore")

    assert audit_registry.check_new_nested(cards) == []


def test_check_new_nested_accepts_a_card_whose_class_is_defined_there(audit_registry, monkeypatch):
    """A card may import the class from the family package that re-exports it."""
    _only_nested(monkeypatch, audit_registry, _NESTED, defined_in={f"{_NESTED}.vector_store"})

    cards = _Cards(f"from {_RAG} import VectorStore")

    assert audit_registry.check_new_nested(cards) == []


def test_check_new_nested_skips_internal_and_alias_packages(audit_registry, monkeypatch):
    internal, alias = f"{_RAG}.internal_helper", f"{_RAG}.alias_of_something"
    _only_nested(monkeypatch, audit_registry, internal, alias)
    monkeypatch.setitem(audit_registry.INTERNAL_ONLY_SUBPACKAGES, internal, "a helper")
    monkeypatch.setitem(audit_registry.ALIAS_SUBPACKAGES, alias, f"{_RAG}.retriever")

    assert audit_registry.check_new_nested(_Cards()) == []


def test_check_new_nested_reads_the_real_gaik_package_layout(audit_registry):
    """Against installed gaik: the nested packages are found, and the one a card
    covers is not reported while a sibling without a card is."""
    pytest.importorskip("gaik.software_components.RAG.vector_store")
    pytest.importorskip("gaik.software_components.RAG.retriever")
    assert _NESTED in audit_registry._gaik_nested_subpackages()

    findings = audit_registry.check_new_nested(_Cards(f"from {_RAG}.retriever import Retriever"))

    reported = {f["component"] for f in findings}
    assert "vector_store" in reported
    assert "retriever" not in reported
