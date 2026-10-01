"""Tests for pricing the fees of an order line."""

from api.utils.order_fees import BomFee, parse_service_rates, price_fees

PRICE_ROWS = [
    ("Service", "Rate", "Description"),
    ("Custom Cutting", "$5.00 - $45.00/cut", "Varies by material"),
    ("Hydrostatic Testing", "$35.00/pipe", "For pressure-rated pipe products"),
    ("Rush Processing (< 5 days)", "+25% surcharge", "Subject to availability"),
    ("Packaging - Export Grade", "$75.00/crate", "Wooden crate"),
    ("Packaging - Standard", "$25.00/pallet", "Shrink-wrapped pallet"),
    ("FOB Origin", "Buyer assumes freight and risk at origin", None),
    (None, None, None),
]


def _fees():
    return [
        BomFee(name="Cutting Fee", applies=True, basis="Per cut", quantity=200),
        BomFee(name="Cert Fee (MTC 3.1)", applies=True, basis="Per heat/lot", quantity=1),
        BomFee(name="Testing Fee", applies=False),
        BomFee(name="Hydrostatic Testing", applies=True, basis="Per pipe", quantity=150),
        BomFee(name="Packaging - Export Grade", applies=True, basis="Per crate", quantity=1250),
        BomFee(name="Rush / Same-Day Processing", applies=False),
    ]


def test_only_flat_rates_are_taken_from_the_services_section():
    rates = parse_service_rates(PRICE_ROWS)

    assert rates["hydrostatictesting"].rate == 35.0
    assert rates["hydrostatictesting"].unit == "pipe"
    assert rates["packagingexportgrade"].rate == 75.0
    assert rates["packagingstandard"].unit == "pallet"
    # A range, a percentage and free text are not one rate.
    assert set(rates) == {"hydrostatictesting", "packagingexportgrade", "packagingstandard"}


def test_applying_fees_are_priced_as_rate_times_quantity():
    charges, notes = price_fees(
        _fees(),
        cutting_rate=5.0,
        testing_rate=15.0,
        certificate_rate=25.0,
        service_rates=parse_service_rates(PRICE_ROWS),
    )

    by_name = {c.name: c for c in charges}
    assert by_name["Cutting Fee"].amount == 1000.0  # 200 cuts x $5
    assert by_name["Cert Fee (MTC 3.1)"].amount == 25.0
    assert by_name["Hydrostatic Testing"].amount == 5250.0  # 150 pipes x $35
    assert by_name["Packaging - Export Grade"].amount == 93750.0  # 1,250 crates x $75
    # A fee that does not apply is not charged.
    assert "Testing Fee" not in by_name
    assert "Rush / Same-Day Processing" not in by_name
    assert notes == []


def test_a_fee_without_a_rate_is_reported_and_not_charged():
    fees = [BomFee(name="Surface Treatment", applies=True, quantity=3)]

    charges, notes = price_fees(
        fees, cutting_rate=5, testing_rate=15, certificate_rate=25, service_rates={}
    )

    assert charges == []
    assert notes == ["No rate found in the price list for 'Surface Treatment'; it was not charged"]


def test_a_missing_quantity_is_charged_once_and_reported():
    fees = [BomFee(name="Cert Fee (MTC 3.1)", applies=True)]

    charges, notes = price_fees(
        fees, cutting_rate=5, testing_rate=15, certificate_rate=25, service_rates={}
    )

    assert [c.amount for c in charges] == [25.0]
    assert notes == ["No quantity stated for 'Cert Fee (MTC 3.1)'; charged once"]
