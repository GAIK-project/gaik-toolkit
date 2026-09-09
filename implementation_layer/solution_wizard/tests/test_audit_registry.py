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


def test_schema_generator_subpackage_is_in_the_alias_list(audit_registry):
    assert (
        audit_registry.ALIAS_SUBPACKAGES["gaik.software_components.schema_generator"]
        == "gaik.software_components.extractor"
    )


def test_schema_generator_alias_reexports_the_canonical_class():
    from gaik.software_components.extractor import SchemaGenerator as CanonicalSchemaGenerator
    from gaik.software_components.schema_generator import SchemaGenerator as AliasSchemaGenerator

    assert AliasSchemaGenerator is CanonicalSchemaGenerator


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
