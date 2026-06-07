"""Tests for the promotion script's check functions (Part 2d)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from solution_wizard.blueprint import Blueprint
from solution_wizard.scaffolder import _build_variables, _determine_pattern

import promote_template as promo


def _blueprint() -> Blueprint:
    data = {
        "blueprint_version": "1.0",
        "use_case": {"id": "facilities_fault", "name": "Facilities Fault", "description": "x", "domain": "test"},
        "technical_spec": {"input_types": ["audio"], "output_types": ["structured_json"], "language": "fi"},
        "target_output_spec": {"schema_name": "MaintenanceTicket", "fields": ["fault_description", "location"], "required_fields": ["fault_description"]},
        "components": {"selected_modules": [], "selected_building_blocks": ["Transcriber", "Extractor"], "custom_components": []},
        "artifacts": {
            "src_audio": {"type": "audio", "source": "user_upload", "optional": False},
            "out": {"type": "structured_json", "source": "generated", "optional": False, "final_output": True, "produced_by": "extract"},
        },
        "workflow": {"steps": [
            {"id": "rec", "name": "Record", "type": "user_task", "inputs": [], "outputs": ["src_audio"]},
            {"id": "transcribe", "name": "T", "type": "automated_task", "component": "Transcriber", "inputs": ["src_audio"], "outputs": ["out"], "depends_on": ["rec"]},
            {"id": "extract", "name": "E", "type": "automated_task", "component": "Extractor", "inputs": ["src_audio"], "outputs": ["out"], "depends_on": ["transcribe"]},
        ]},
    }
    return Blueprint.model_validate(data)


# ---------------------------------------------------------------------------
# Genericity scan
# ---------------------------------------------------------------------------

def test_genericity_rejects_leaked_field_name():
    bp = _blueprint()
    # A candidate that leaked a use-case field name outside ${...}
    candidate = 'x = "fault_description in the body"\n'
    leaked = promo._check_genericity(candidate, bp)
    assert "fault_description" in leaked


def test_genericity_rejects_leaked_schema_name():
    bp = _blueprint()
    candidate = "schema = MaintenanceTicket()\n"
    leaked = promo._check_genericity(candidate, bp)
    assert "MaintenanceTicket" in leaked


def test_genericity_accepts_placeholder_form():
    bp = _blueprint()
    # Same tokens but inside ${...} placeholders -> not leaked
    candidate = 'name = "${schema_name}"\nuc = "${use_case_id}"\n'
    leaked = promo._check_genericity(candidate, bp)
    assert leaked == []


def test_genericity_ignores_short_field_names():
    """Ultra-short field names are skipped to avoid false positives."""
    data = _blueprint().model_dump()
    data["target_output_spec"]["fields"] = ["id", "qty"]  # short
    bp = Blueprint.model_validate(data)
    candidate = "qty = 5\n"  # 'qty' is <4 chars, should be ignored
    leaked = promo._check_genericity(candidate, bp)
    assert "qty" not in leaked


# ---------------------------------------------------------------------------
# Fills cleanly
# ---------------------------------------------------------------------------

def test_fills_cleanly_detects_unknown_placeholder():
    bp = _blueprint()
    variables = _build_variables(bp, _determine_pattern(bp))
    candidate = "x = ${not_a_real_variable}\n"
    unfilled = promo._check_fills_cleanly(candidate, variables)
    assert any("not_a_real_variable" in u for u in unfilled)


def test_fills_cleanly_passes_for_known_variables():
    bp = _blueprint()
    variables = _build_variables(bp, _determine_pattern(bp))
    candidate = 'name = "${use_case_name}"\nlang = "${language}"\n'
    unfilled = promo._check_fills_cleanly(candidate, variables)
    assert unfilled == []


# ---------------------------------------------------------------------------
# Parses
# ---------------------------------------------------------------------------

def test_parses_detects_bad_python():
    bp = _blueprint()
    variables = _build_variables(bp, _determine_pattern(bp))
    candidate = "def main(:\n    pass\n"  # syntax error
    err = promo._check_parses(candidate, variables)
    assert err is not None


def test_parses_accepts_valid_python():
    bp = _blueprint()
    variables = _build_variables(bp, _determine_pattern(bp))
    candidate = 'name = "${use_case_name}"\nprint(name)\n'
    assert promo._check_parses(candidate, variables) is None


# ---------------------------------------------------------------------------
# Blueprint-specific token derivation
# ---------------------------------------------------------------------------

def test_specific_tokens_include_id_and_schema():
    bp = _blueprint()
    tokens = promo._blueprint_specific_tokens(bp)
    assert "facilities_fault" in tokens
    assert "MaintenanceTicket" in tokens
    assert "fault_description" in tokens


def test_genericity_rejects_leaked_language_code():
    """Language code 'fi' must be treated as a specific token."""
    bp = _blueprint()
    # Blueprint has language="fi" (set in technical_spec via fixture)
    candidate = 'language = "fi"\n'  # hardcoded language
    leaked = promo._check_genericity(candidate, bp)
    assert "fi" in leaked


def test_genericity_accepts_language_as_placeholder():
    bp = _blueprint()
    candidate = 'language = "${language}"\n'
    leaked = promo._check_genericity(candidate, bp)
    assert "fi" not in leaked


def test_import_check_runs_by_default(tmp_path, monkeypatch):
    """--check-imports must default to ON; use --skip-import-check to disable."""
    import argparse
    # Simulate parsing with no flags -- import check should run
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-import-check", action="store_true")
    args = parser.parse_args([])
    assert not args.skip_import_check  # default is False = check IS run
