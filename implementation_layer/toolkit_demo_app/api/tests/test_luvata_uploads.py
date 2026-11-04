"""The purchase-order routes check what they are sent, not only what the page sends."""

import asyncio
import io
import sys

import pytest
from api.routers import luvata_order
from fastapi import HTTPException, UploadFile


def _upload(data: bytes, name: str = "po.pdf") -> UploadFile:
    return UploadFile(filename=name, file=io.BytesIO(data))


def test_a_file_that_is_not_a_pdf_is_refused():
    with pytest.raises(HTTPException) as err:
        asyncio.run(luvata_order._parse_upload(_upload(b"plain text", "fake.pdf"), "po"))
    assert err.value.status_code == 400
    assert err.value.detail == "fake.pdf is not a PDF"


def test_a_pdf_over_the_size_limit_is_refused(monkeypatch):
    limits = sys.modules[luvata_order.validate_file_size.__module__]
    monkeypatch.setattr(limits, "MAX_FILE_SIZE_BYTES", 8)
    with pytest.raises(HTTPException) as err:
        asyncio.run(luvata_order._parse_upload(_upload(b"%PDF-1.7 and more"), "po"))
    assert err.value.status_code == 413


def test_process_refuses_more_boms_than_the_page_allows():
    async def events() -> str:
        response = await luvata_order.process_order(
            po_file=_upload(b"%PDF-1.7"),
            bom_files=[_upload(b"%PDF-1.7", f"bom{i}.pdf") for i in range(11)],
            pricing_file=_upload(b"price list", "prices.xlsx"),
        )
        return "".join([str(chunk) async for chunk in response.body_iterator])

    body = asyncio.run(events())
    assert f"At most {luvata_order.MAX_CUSTOM_BOMS} BOMs" in body
    assert "Parsing documents" not in body
