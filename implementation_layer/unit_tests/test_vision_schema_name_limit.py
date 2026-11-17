"""VisionExtractor sends a schema name of at most 64 characters.

OpenAI and Azure take the response model's class name as
``response_format.json_schema.name`` and refuse one over 64 characters with a 400
("string too long"). With ``include_verification=True`` the class name grew by
``_Verifiable``, so a 56-character name from the schema generator became 67.
"""

from __future__ import annotations

from gaik.software_components.vision_extractor import vision_extractor as ve
from pydantic import BaseModel, create_model

LONG = "customer_purchase_order_erp_compatible_record_Extraction"  # 56 characters


def _model(name: str) -> type[BaseModel]:
    return create_model(name, order_number=(str, ...), total=(float | None, None))


def test_the_verification_wrapper_keeps_the_name_within_64_characters():
    wrapped = ve._wrap_model_for_verification(_model(LONG))

    assert len(wrapped.__name__) <= 64
    assert wrapped.__name__.endswith("_Verifiable")
    assert set(wrapped.model_fields) == {"order_number", "total"}


def test_a_long_model_name_is_shortened_and_the_model_still_validates():
    model = _model("A" * 70)

    bounded = ve._within_schema_name_limit(model)

    assert len(bounded.__name__) <= 64
    assert bounded.model_validate({"order_number": "PO-1"}).model_dump() == {
        "order_number": "PO-1",
        "total": None,
    }
    short = _model("Order")
    assert ve._within_schema_name_limit(short) is short


def test_a_name_with_letters_outside_ascii_is_made_acceptable():
    model = _model("Päätös_Extraction")

    bounded = ve._within_schema_name_limit(model)

    assert bounded.__name__.isascii()
    assert bounded.model_validate({"order_number": "PO-1"}).order_number == "PO-1"


def test_the_shared_provider_path_sends_a_name_within_64_characters(monkeypatch, tmp_path):
    sent = {}

    class _Client:
        raw = None

        def chat_parsed(self, messages, *, response_format, **options):
            sent["name"] = response_format.__name__
            return response_format.model_construct()

    import gaik.software_components.llm as llm
    from gaik.software_components.parsers.multimodal_parser import chat_content

    monkeypatch.setattr(llm, "create_llm_client", lambda config: _Client())
    monkeypatch.setattr(chat_content, "build_chat_document_content", lambda *a, **k: "page")
    extractor = ve.VisionExtractor.__new__(ve.VisionExtractor)
    extractor.config = {}
    extractor.model = "m"
    extractor.model_provider = "azure"
    extractor.limits = None

    wrapped = ve._wrap_model_for_verification(_model(LONG))
    extractor._call_shared([tmp_path / "po.pdf"], "system", "user", wrapped)

    assert len(sent["name"]) <= 64
