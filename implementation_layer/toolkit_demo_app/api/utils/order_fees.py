"""Fees of a purchase order line, priced from the price list.

The extraction returns, per line, the additional fees that apply, with their charge
basis and quantity. Each is priced as rate x quantity. Cutting, testing and certificate
fees use the rates in the material's price list row; other services (hydrostatic
testing, packaging) use the flat rates of the price list's services section.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

FeeKind = Literal["cutting", "testing", "certificate", "other"]


class BomFee(BaseModel):
    """A fee that applies to a line, as the extraction found it."""

    name: str
    applies: bool
    basis: str | None = None
    quantity: float | None = None
    notes: str | None = None


class ServiceRate(BaseModel):
    """A flat rate from the price list's services section, such as $35.00/pipe."""

    name: str
    rate: float
    unit: str


class FeeCharge(BaseModel):
    """A fee charged on an order line."""

    name: str
    kind: FeeKind
    basis: str | None = None
    quantity: float
    rate: float
    amount: float


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


_FLAT_RATE = re.compile(r"^\$\s*(\d[\d,]*(?:\.\d+)?)\s*/\s*([A-Za-z][A-Za-z ]*?)\s*$")


def parse_service_rates(rows: list[tuple | list]) -> dict[str, ServiceRate]:
    """Flat "$X/unit" rates from the price list's rows, keyed by service name.

    Ranges ("$5.00 - $45.00/cut") and percentages ("+25% surcharge") are left out: they
    do not give one rate.
    """
    rates: dict[str, ServiceRate] = {}
    for row in rows:
        if len(row) < 2 or row[0] is None or row[1] is None:
            continue
        match = _FLAT_RATE.match(str(row[1]).strip())
        if match:
            name = str(row[0]).strip()
            rates[_key(name)] = ServiceRate(
                name=name, rate=float(match.group(1).replace(",", "")), unit=match.group(2)
            )
    return rates


def _find_service_rate(name: str, rates: dict[str, ServiceRate]) -> ServiceRate | None:
    key = _key(name)
    if key in rates:
        return rates[key]
    return next((rate for k, rate in rates.items() if k in key or key in k), None)


def price_fees(
    fees: list[BomFee],
    *,
    cutting_rate: float,
    testing_rate: float,
    certificate_rate: float,
    service_rates: dict[str, ServiceRate],
) -> tuple[list[FeeCharge], list[str]]:
    """The charges for the fees that apply, and notes on any that could not be priced."""
    charges: list[FeeCharge] = []
    notes: list[str] = []
    for fee in fees:
        if not fee.applies:
            continue
        name = fee.name.lower()
        kind: FeeKind
        if name.startswith("cutting"):
            kind, rate = "cutting", cutting_rate
        elif "cert" in name:
            kind, rate = "certificate", certificate_rate
        elif name.startswith("testing"):
            kind, rate = "testing", testing_rate
        else:
            service = _find_service_rate(fee.name, service_rates)
            kind, rate = "other", service.rate if service else 0.0
        if rate <= 0:
            notes.append(f"No rate found in the price list for '{fee.name}'; it was not charged")
            continue
        quantity = fee.quantity
        if quantity is None:
            notes.append(f"No quantity stated for '{fee.name}'; charged once")
            quantity = 1.0
        charges.append(
            FeeCharge(
                name=fee.name,
                kind=kind,
                basis=fee.basis,
                quantity=quantity,
                rate=round(rate, 2),
                amount=round(rate * quantity, 2),
            )
        )
    return charges, notes
