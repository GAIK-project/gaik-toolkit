"""
Auto-generated schema module (do not edit manually).
"""

import decimal
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict

class Ty_maap_iv_kirja_kenttien_poiminta_nitallenteesta_Extraction(BaseModel):
    """Extraction model for Työmaapäiväkirja kenttien poiminta äänitallenteesta"""
    model_config = ConfigDict(extra='forbid')

    kohde: str | None = Field(None, description="Kohde [Subject of the diary]")
    laatija: str | None = Field(None, description="Laatija [Name of the author recording the diary]")
    saa: str | None = Field(None, description="Sää [e.g., 3 °C, 2 m/s, 78 % suht. kosteus, Kp: -1.4 C]")
    paivamaara: str | None = Field(None, description="Päivämäärä [Format: dd.mm.yyyy]")
    resurssit_henkilosto: str | None = Field(None, description="Resurssit - Henkilöstö [e.g., Työnjohtajat: 2 hlö, Työntekijät: 1 hlö, Alihankkijat: 4 hlö, Yhteensä: 7 hlö]")
    tyoviikko: int | None = Field(None, description="Työviikko [Week number, e.g., 2]")
    paivan_tyot_omat_tyot: list[str] | None = Field(None, description="Päivän työt (Omat työt) [List all works]")
    paivan_tapahtumat: str | None = Field(None, description="Päivän tapahtumat")
    liitteet: str | None = Field(None, description="Liitteet [number and type of attachments, e.g., 4 photos, 1 email attachment]")
    valvojan_huomiot: str | None = Field(None, description="Valvojan huomiot")
    paivan_poikkeamat: str | None = Field(None, description="Päivän poikkeamat")
    aloitetut_tyovaiheet: list[str] | None = Field(None, description="Aloitetut työvaiheet")
    kaynnissa_olevat_tyovai: list[str] | None = Field(None, description="Käynnissä olevat työvai")
    paattyneet_tyovai: list[str] | None = Field(None, description="Päättyneet työvai")
    keskeytyneet_tyovai: list[str] | None = Field(None, description="Keskeytyneet työvai")
    pyydetyt_lisajat: str | None = Field(None, description="Pyydetyt lisäajat")
    tehdyt_katselmukset: str | None = Field(None, description="Tehdyt katselmukset")
    valvojan_huomautukset: str | None = Field(None, description="Valvojan huomautukset")
    valvojan_allekirjoitus: str | None = Field(None, description="Valvojan allekirjoitus")
    vastaavan_allekirjoitus: str | None = Field(None, description="Vastaavan allekirjoitus")
