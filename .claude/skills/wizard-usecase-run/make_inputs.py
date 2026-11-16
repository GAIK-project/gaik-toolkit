"""Build the sample inputs in inputs/ that usecases.json lists for the PoC test run.

    python make_inputs.py            # the PDF, XLSX and text files, the same bytes each time
    python make_inputs.py --audio    # also the two recordings: needs uvx and ffmpeg

The first needs the standard library only. Everything is invented: the organisations,
people, addresses and figures exist nowhere.

The recordings are synthetic speech (Piper, the CC0 Finnish voice fi_FI-harri-medium)
encoded to MP3 with ffmpeg; they differ slightly from one build to the next, so rebuild
them only when the spoken text below changes.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
import zipfile
from datetime import date, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent / "inputs"
VOICE = "fi_FI-harri-medium"

# -- PDF: one A4 page of text, Helvetica, a real cross-reference table ---------


def pdf(lines: list[str]) -> bytes:
    """A one-page PDF with a text layer. A line starting with '# ' is set as a heading."""
    content = ["BT", "72 780 Td"]
    for line in lines:
        size = 16 if line.startswith("# ") else 11
        text = line.removeprefix("# ").encode("cp1252")
        for char in (b"\\", b"(", b")"):
            text = text.replace(char, b"\\" + char)
        content += [f"/F1 {size} Tf", f"({text.decode('latin-1')}) Tj", f"0 -{size + 6} Td"]
    content.append("ET")
    stream = "\n".join(content).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


def invoice(number: str, day: str, due: str, reference: str, rows: list[tuple]) -> bytes:
    net = sum(quantity * price for _, quantity, price in rows)
    vat = round(net * 0.255, 2)

    def eur(amount: float) -> str:
        return f"{amount:.2f}".replace(".", ",") + " EUR"

    lines = [
        "# LASKU",
        "",
        "Toimittaja: Mallikylän Toimistotarvike Oy (keksitty yritys)",
        "Esimerkkikatu 1, 00000 Mallikylä",
        "",
        "Asiakas: Esimerkkilän Tilipalvelu Oy (keksitty yritys)",
        "Kuvitteellinentie 2, 00000 Esimerkkilä",
        "",
        f"Laskun numero: {number}",
        f"Laskun päiväys: {day}",
        f"Eräpäivä: {due}",
        f"Viitenumero: {reference}",
        "Maksuehto: 14 päivää netto",
        "",
        "Tuote                              Määrä    Yksikköhinta      Yhteensä",
    ]
    lines += [
        f"{name:<34} {quantity:>5}    {eur(price):>12}  {eur(quantity * price):>12}"
        for name, quantity, price in rows
    ]
    lines += [
        "",
        f"Veroton summa: {eur(net)}",
        f"Arvonlisävero 25,5 %: {eur(vat)}",
        f"Loppusumma: {eur(net + vat)}",
    ]
    return pdf(lines)


EARLIER_REPORT = [
    "# KUNTOTARKASTUSRAPORTTI 2021",
    "",
    "Kohde: Asunto Oy Mallikylän Esimerkkitie 1 (keksitty kohde)",
    "Rakennusvuosi: 1984. Kerrosala: 1 240 m2. Kolme kerrosta, 18 huoneistoa.",
    "Tarkastuspäivä: 12.5.2021. Tarkastaja: Maija Mallinen (keksitty henkilö).",
    "",
    "Rakenteet: Tiilivuorattu betonirunko. Julkisivun saumoissa paikoin halkeamia.",
    "Vesikatto: Bitumikermikate uusittu vuonna 2009, kunto tyydyttävä.",
    "Ikkunat: Alkuperäiset puuikkunat, ulkopuitteissa maalipinnan hilseilyä.",
    "",
    "LVI: Käyttövesiputket alkuperäiset kupariputket. Viemärit valurautaa.",
    "Lämmönjakokeskus uusittu vuonna 2012. Ilmanvaihto koneellinen poisto.",
    "",
    "Sähkö: Ryhmäkeskukset alkuperäiset. Nousujohdot uusittu vuonna 2015.",
    "",
    "Havaitut riskit: Pesuhuoneiden vedeneristys alkuperäinen, kosteusvaurion riski.",
    "Suositukset: Ikkunoiden kunnostus 2022-2024. Käyttövesiputkien kuntotutkimus 2023.",
]

NOTES = """Kuntotarkastuksen muistiinpanot (keksitty kohde ja keksityt henkilöt)

Kohde: Asunto Oy Mallikylän Esimerkkitie 1
Tarkastuspäivä: 3.11.2026
Tarkastaja: Veikko Esimerkki

Rakenteet
- Julkisivun elementtisaumat halkeilleet etelä- ja länsisivulla, sauman ikä noin 20 vuotta.
- Sokkelissa kosteusjälki B-rapun kohdalla, syöksytorven alapää irti sadevesikaivosta.
- Vesikaton kermin saumat ehjät, läpivientien tiivisteissä haurastumaa.

LVI
- Käyttövesiputkissa vihreää hapettumaa liitoksissa kellarin jakotukilla.
- Viemärin tuuletusputken hattu puuttuu.
- Ilmanvaihdon poistokoneen laakeriääni voimakas, suodattimet vaihdettu 2025.

Sähkö
- Ryhmäkeskuksissa tulppasulakkeet, vikavirtasuojat puuttuvat huoneistoista A1-A6.
- Porrasvalaistuksen ajastin ei toimi C-rapussa.

Muuta
- Pesuhuoneiden kosteusmittaus huoneistoissa A2 ja B4: A2 normaali, B4 kohonnut lattiakaivolla.
- Autopaikkojen lämmitystolppia ei tarkastettu.
"""

# -- XLSX: one sheet, real date cells, inline strings ----------------------------

CUSTOMERS = [
    "Kuvitteellinen Konepaja Oy",
    "Mallikylän Rauta Oy",
    "Esimerkkilän Leipomo Oy",
    "Satuvaaran Kuljetus Oy",
]
PRODUCTS = [("Porakone P200", 189.0), ("Ruuvisarja R40", 24.5), ("Työhanskat T7", 12.9)]
SELLERS = ["Aino Mallinen", "Veikko Esimerkki", "Sanni Testilä"]


def sales_rows() -> list[tuple]:
    """45 sales rows from October 2025 to March 2026, the same every time."""
    rows = []
    day = date(2025, 10, 2)
    for i in range(45):
        product, price = PRODUCTS[i % 3]
        rows.append(
            (day, CUSTOMERS[(i * 3) % 4], product, 1 + (i * 7) % 12, price, SELLERS[(i * 5) % 3])
        )
        day += timedelta(days=4)
    return rows


def xlsx(header: list[str], rows: list[tuple]) -> bytes:
    def cell(ref: str, value) -> str:
        if isinstance(value, date):
            return f'<c r="{ref}" s="1"><v>{(value - date(1899, 12, 30)).days}</v></c>'
        if isinstance(value, (int, float)):
            return f'<c r="{ref}"><v>{value}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'

    sheet_rows = []
    for r, row in enumerate([tuple(header), *rows], 1):
        cells = "".join(cell(f"{'ABCDEFGH'[c]}{r}", value) for c, value in enumerate(row))
        sheet_rows.append(f'<row r="{r}">{cells}</row>')
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    package = "http://schemas.openxmlformats.org/package/2006"
    kind = "application/vnd.openxmlformats"
    sheet = f"{kind}-officedocument.spreadsheetml"
    head = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    parts = {
        "[Content_Types].xml": f'<Types xmlns="{package}/content-types">'
        f'<Default Extension="rels" ContentType="{kind}-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'<Override PartName="/xl/workbook.xml" ContentType="{sheet}.sheet.main+xml"/>'
        f'<Override PartName="/xl/worksheets/sheet1.xml" ContentType="{sheet}.worksheet+xml"/>'
        f'<Override PartName="/xl/styles.xml" ContentType="{sheet}.styles+xml"/>'
        "</Types>",
        "_rels/.rels": f'<Relationships xmlns="{package}/relationships">'
        f'<Relationship Id="rId1" Type="{rel}/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>",
        "xl/workbook.xml": f'<workbook xmlns="{main}" xmlns:r="{rel}">'
        '<sheets><sheet name="Myynti" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": f'<Relationships xmlns="{package}/relationships">'
        f'<Relationship Id="rId1" Type="{rel}/worksheet" Target="worksheets/sheet1.xml"/>'
        f'<Relationship Id="rId2" Type="{rel}/styles" Target="styles.xml"/>'
        "</Relationships>",
        "xl/styles.xml": f'<styleSheet xmlns="{main}">'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
        "</cellStyleXfs>"
        '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="14" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
        "</cellXfs></styleSheet>",
        "xl/worksheets/sheet1.xml": f'<worksheet xmlns="{main}"><sheetData>'
        + "".join(sheet_rows)
        + "</sheetData></worksheet>",
    }
    with tempfile.TemporaryFile() as target:
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, xml in parts.items():
                # A fixed timestamp and creating system keep the file's bytes the
                # same from build to build and on every OS: ZipInfo takes the system
                # from the OS it runs on (0 on Windows, 3 on macOS and Linux).
                info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.create_system = 0
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, head + xml)
        target.seek(0)
        return target.read()


# -- audio: synthetic Finnish speech ----------------------------------------------

SPOKEN = {
    "site-diary.mp3": (
        "Työmaapäiväkirja, torstai kahdestoista marraskuuta. "
        "Sää: pilvistä, kaksi astetta lämmintä, heikkoa tuulta. "
        "Työmaan vahvuus: kahdeksan omaa työntekijää ja kolme aliurakoitsijan asentajaa. "
        "Tehdyt työvaiheet: toisen kerroksen väliseinien runkotyöt saatiin valmiiksi, "
        "ja kolmannen kerroksen holvin muotitus aloitettiin. "
        "Poikkeamat: betonitoimitus myöhästyi puolitoista tuntia. "
        "Huomiot: itäpäädyn telineen kaide korjattiin aamulla. "
        "Huomisen suunnitelma: holvin raudoitus ja sähköputkitus."
    ),
    "condition-dictation.mp3": (
        "Sanelu kuntotarkastuksesta, Asunto Osakeyhtiö Mallikylän Esimerkkitie yksi. "
        "Kellarin lämmönjakohuoneessa on lattialla vesilammikko paisunta-astian alla. "
        "Ullakon yläpohjan eristeessä on tummentumaa savupiipun juuressa. "
        "A-rapun ulko-oven yläpuolinen katos on ruostunut kiinnityksistään."
    ),
}


def speak(text: str, target: Path) -> None:
    with tempfile.TemporaryDirectory() as work:
        piper = ["uvx", "--from", "piper-tts", "python", "-m"]
        subprocess.run([*piper, "piper.download_voices", VOICE], cwd=work, check=True)
        subprocess.run(
            [*piper, "piper", "-m", VOICE, "-f", "speech.wav"],
            cwd=work,
            input=text.encode("utf-8"),
            check=True,
        )
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(Path(work) / "speech.wav")]
            + ["-ac", "1", "-ar", "16000", "-b:a", "32k", "-map_metadata", "-1", "-bitexact"]
            + [str(target)],
            check=True,
        )


# -- Staff policies for the question answering case: invented, one page each ----

LEAVE_POLICY = [
    "# Lomaohje",
    "Esimerkki Oy, henkilöstöohje 4, voimassa 1.1.2026 alkaen",
    "",
    "Vuosiloma",
    "Lomaa kertyy 2,5 arkipäivää jokaiselta täydeltä lomanmääräytymiskuukaudelta.",
    "Kesäloma pidetään 2.5.-30.9. ja talviloma 1.10.-30.4.",
    "",
    "Loman hakeminen",
    "Kesälomatoive jätetään esihenkilölle maaliskuun loppuun mennessä.",
    "Esihenkilö vahvistaa lomat huhtikuun 15. päivään mennessä.",
    "",
    "Loman siirtäminen",
    "Jos työntekijä sairastuu loman aikana, loma siirretään pyynnöstä.",
    "Siirtoa pyydetään esihenkilöltä viipymättä, ja sairaudesta tarvitaan lääkärintodistus.",
    "",
    "Säästövapaa",
    "18 päivää ylittävän osan lomasta voi sopia pidettäväksi säästövapaana.",
]

REMOTE_WORK_POLICY = [
    "# Etätyöohje",
    "Esimerkki Oy, henkilöstöohje 7, voimassa 1.3.2026 alkaen",
    "",
    "Etätyön määrä",
    "Etätyötä voi tehdä enintään kolme päivää viikossa, kun tehtävät sen sallivat.",
    "Tiistai on koko henkilöstön yhteinen toimistopäivä.",
    "",
    "Sopiminen",
    "Etätyöstä sovitaan esihenkilön kanssa kirjallisesti ennen sen aloittamista.",
    "Sopimus tarkistetaan kehityskeskustelussa kerran vuodessa.",
    "",
    "Työvälineet",
    "Työnantaja antaa kannettavan tietokoneen, näytön ja kuulokkeet.",
    "Kodin verkkoyhteydestä vastaa työntekijä itse.",
    "",
    "Tietoturva",
    "Etätyössä käytetään aina VPN-yhteyttä, eikä työasioita käsitellä julkisissa tiloissa.",
    "",
    "Ulkomailta tehtävä etätyö",
    "Ulkomailta saa työskennellä enintään 14 päivää vuodessa, ja siihen tarvitaan HR:n lupa.",
]

# Four the policies answer, two they do not (mileage, sick pay).
POLICY_QUESTIONS = """\
Kuinka monta lomapäivää kertyy kuukaudessa?
Mihin mennessä kesälomatoive pitää jättää?
Kuinka monta päivää viikossa saan tehdä etätyötä?
Tarvitsenko luvan, jos teen etätyötä ulkomailta?
Paljonko kilometrikorvaus on oman auton käytöstä?
Maksetaanko sairauspoissaolon ajalta palkkaa?
"""


# What a sales manager asks of the sheet, one question a line.
SALES_QUESTIONS = """Mikä on myynnin arvo yhteensä?
Kuka myyjä myi eniten euroissa?
Mitä tuotetta myytiin kappalemääräisesti eniten?
Mikä asiakas osti eniten euroissa?
"""


def generated() -> dict[str, bytes]:
    """Every input this script builds without --audio, by file name."""
    return {
        "policy-leave.pdf": pdf(LEAVE_POLICY),
        "policy-remote-work.pdf": pdf(REMOTE_WORK_POLICY),
        "policy-questions.txt": POLICY_QUESTIONS.encode("utf-8"),
        "invoice-1001.pdf": invoice(
            "1001",
            "3.11.2026",
            "17.11.2026",
            "10016",
            [("Kopiopaperi A4, 5 x 500 arkkia", 12, 24.90), ("Mustekasetti MK-12", 4, 39.00)],
        ),
        "invoice-1002.pdf": invoice(
            "1002",
            "10.11.2026",
            "24.11.2026",
            "10029",
            [("Arkistokansio, 20 kpl", 3, 31.50), ("Työtuoli Malli T", 2, 219.00)],
        ),
        "condition-earlier-report.pdf": pdf(EARLIER_REPORT),
        "condition-notes.txt": NOTES.encode("utf-8"),
        "sales-questions.txt": SALES_QUESTIONS.encode("utf-8"),
        "sales-rows.xlsx": xlsx(
            ["Päivämäärä", "Asiakas", "Tuote", "Määrä", "Yksikköhinta", "Myyjä"], sales_rows()
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--audio", action="store_true", help="also rebuild the two recordings")
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    for name, data in generated().items():
        (OUT / name).write_bytes(data)
        print(f"{name}: {len(data)} bytes")
    if args.audio:
        for tool in ("uvx", "ffmpeg"):
            if not shutil.which(tool):
                raise SystemExit(f"--audio needs {tool} on the PATH")
        for name, text in SPOKEN.items():
            speak(text, OUT / name)
            print(f"{name}: {(OUT / name).stat().st_size} bytes")


if __name__ == "__main__":
    main()
