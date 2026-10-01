"""Field names that the schema generator reduced to ASCII get their letters back."""

from api.utils.field_names import (
    field_name_mapping,
    rename_described_fields,
    rename_keys,
    restore_field_names,
)
from pydantic import BaseModel, Field


def test_names_with_underscores_for_missing_letters_are_restored_from_the_prompt():
    prompt = """Poimi seuraavat tiedot:
- Päivämäärä (milloin tapahtui)
- Tehdyt välittömät toimenpiteet
- Ehdotukset vastaavien tilanteiden välttämiseksi"""
    generated = {
        "p_iv_m_r",
        "tehdyt_v_litt_m_t_toimenpiteet",
        "ehdotukset_vastaavien_tilanteiden_v_ltt_miseksi",
    }

    assert restore_field_names(generated, [prompt]) == {
        "p_iv_m_r": "päivämäärä",
        "tehdyt_v_litt_m_t_toimenpiteet": "tehdyt_välittömät_toimenpiteet",
        "ehdotukset_vastaavien_tilanteiden_v_ltt_miseksi": (
            "ehdotukset_vastaavien_tilanteiden_välttämiseksi"
        ),
    }


def test_plain_ascii_names_of_finnish_phrases_get_their_letters_too():
    assert restore_field_names({"paivamaara", "tyonantaja"}, ["Päivämäärä, Työnantaja"]) == {
        "paivamaara": "päivämäärä",
        "tyonantaja": "työnantaja",
    }


def test_names_without_a_matching_phrase_stay_as_they_are():
    assert restore_field_names({"p_iv_m_r", "location"}, ["Where did it happen"]) == {}


def test_english_names_are_not_touched():
    assert restore_field_names({"invoice_number"}, ["Invoice number, total"]) == {}


def test_descriptions_can_supply_the_spelling():
    class Item(BaseModel):
        p_iv_m_r: str | None = Field(default=None, description="Päivämäärä. Creation date.")
        ty_nantaja: str | None = Field(default=None, description="Työnantaja. Yrityksen nimi.")

    assert field_name_mapping(Item, "Poimi tiedot.") == {
        "p_iv_m_r": "päivämäärä",
        "ty_nantaja": "työnantaja",
    }


def test_nested_records_are_included():
    class Row(BaseModel):
        kirjaaja_nimi: str | None = None
        tekop_iv: str | None = Field(default=None, description="Tekopäivä. Päivä.")

    class Collection(BaseModel):
        rivit: list[Row] = Field(default_factory=list)

    assert field_name_mapping(Collection, "") == {"tekop_iv": "tekopäivä"}


def test_keys_are_renamed_at_every_depth_without_overwriting():
    mapping = {"p_iv_m_r": "päivämäärä"}

    renamed = rename_keys(
        [{"incidents": [{"p_iv_m_r": "3.2.2026", "x": 1}]}, {"p_iv_m_r": 1, "päivämäärä": 2}],
        mapping,
    )

    assert renamed == [
        {"incidents": [{"päivämäärä": "3.2.2026", "x": 1}]},
        {"p_iv_m_r": 1, "päivämäärä": 2},
    ]


def test_the_schema_listing_gets_the_restored_names_with_their_children():
    fields = [
        {
            "name": "incidents",
            "type": "list[x]",
            "description": "",
            "children": [{"name": "p_iv_m_r", "type": "str", "description": "Päivämäärä"}],
        }
    ]

    renamed = rename_described_fields(fields, {"p_iv_m_r": "päivämäärä"})

    assert renamed[0]["children"][0]["name"] == "päivämäärä"
    assert fields[0]["children"][0]["name"] == "p_iv_m_r"  # the input is not changed
