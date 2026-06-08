"""Regression tests for Luvata BOM fee-flag resolution.

Guards against the bug where a BOM PDF that is silent about a fee made the LLM
extraction return ``cutting_required=None`` (its schema fields are ``bool |
None``). The old ``fee_flags[key] or bom_data.get(key, False)`` expression then
evaluated to ``None`` (because ``dict.get`` ignores the default when the key is
*present* with value ``None``), and the strict ``BOMData`` model raised:

    1 validation error for BOMData / cutting_required
    Input should be a valid boolean [type=bool_type, input_value=None]

Run standalone (no pytest needed):
    .venv/Scripts/python.exe -m api.tests.test_luvata_fee_flags
"""

from pydantic import ValidationError

from api.routers.luvata_order import BOMData, _resolve_fee_flag


def test_resolve_fee_flag_never_returns_none():
    # The exact failure case: deterministic scan found nothing (False) and the
    # LLM extraction returned the key explicitly as None.
    assert _resolve_fee_flag(False, None) is False
    # Key absent from the extraction dict -> bom_data.get(...) is None.
    assert _resolve_fee_flag(False, None) is False
    # Truthy on either side wins.
    assert _resolve_fee_flag(True, None) is True
    assert _resolve_fee_flag(False, True) is True
    assert _resolve_fee_flag(True, True) is True
    # Explicit False on both stays False.
    assert _resolve_fee_flag(False, False) is False


def test_bomdata_builds_when_extraction_has_none_flags():
    """An all-None extraction must not crash BOMData construction."""
    bom_data = {
        "material_id": "MED-001",
        "cutting_required": None,
        "testing_required": None,
        "certificates_required": None,
    }
    fee_flags = {
        "cutting_required": False,
        "testing_required": False,
        "certificates_required": False,
    }
    bom = BOMData(
        material_id=bom_data.get("material_id", ""),
        type_designation=bom_data.get("type_designation", ""),
        dimensions=bom_data.get("dimensions", ""),
        material_grade=bom_data.get("material_grade", ""),
        cutting_required=_resolve_fee_flag(
            fee_flags["cutting_required"], bom_data.get("cutting_required")
        ),
        testing_required=_resolve_fee_flag(
            fee_flags["testing_required"], bom_data.get("testing_required")
        ),
        certificates_required=_resolve_fee_flag(
            fee_flags["certificates_required"], bom_data.get("certificates_required")
        ),
    )
    assert bom.cutting_required is False
    assert bom.testing_required is False
    assert bom.certificates_required is False


def test_raw_none_still_rejected_by_model():
    """Sanity check: the model itself is strict; None must be coerced upstream."""
    try:
        BOMData(
            material_id="X",
            type_designation="",
            dimensions="",
            material_grade="",
            cutting_required=None,
        )
    except ValidationError:
        pass
    else:  # pragma: no cover - would mean the model silently accepts None
        raise AssertionError("BOMData unexpectedly accepted cutting_required=None")


if __name__ == "__main__":
    test_resolve_fee_flag_never_returns_none()
    test_bomdata_builds_when_extraction_has_none_flags()
    test_raw_none_still_rejected_by_model()
    print("All Luvata fee-flag regression tests passed.")
