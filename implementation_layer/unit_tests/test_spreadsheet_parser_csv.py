"""SpreadsheetParser reads a CSV's delimiter and text encoding.

Excel saves a CSV with ";" between fields in a locale whose decimal separator is a comma
(Finnish, German, ...), and in the Windows "ANSI" code page (cp1252) unless "CSV UTF-8"
is chosen.
"""

from __future__ import annotations

import pytest
from gaik.software_components.parsers.spreadsheet_parser import SpreadsheetParser

FINNISH_CSV = "Tuote;Määrä;Hinta\r\nMaito;2;1,49\r\nLeipä;1;2,10\r\n"
FINNISH_TABLE = (
    "| Row | Tuote | Määrä | Hinta |\n"
    "| --- | --- | --- | --- |\n"
    "| 2 | Maito | 2 | 1,49 |\n"
    "| 3 | Leipä | 1 | 2,10 |"
)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "cp1252", "utf-16"])
def test_csv_from_excel_in_a_finnish_locale(tmp_path, encoding):
    # Excel writes ";" where the decimal separator is a comma, as "ANSI" (cp1252),
    # "CSV UTF-8" (with a byte order mark) or "Unicode text" (UTF-16).
    path = tmp_path / "hinnat.csv"
    path.write_bytes(FINNISH_CSV.encode(encoding))

    assert SpreadsheetParser().parse_spreadsheet(path) == FINNISH_TABLE


def test_csv_in_utf16_without_a_byte_order_mark(tmp_path):
    path = tmp_path / "hinnat.csv"
    path.write_bytes(FINNISH_CSV.encode("utf-16-le"))

    assert SpreadsheetParser().parse_spreadsheet(path) == FINNISH_TABLE


def test_a_cp1252_csv_is_logged_as_read_in_that_code_page(tmp_path, caplog):
    path = tmp_path / "Virtanen_hinnat.csv"
    path.write_bytes("Tuote;Hinta\nKahvi;4,90 €\n".encode("cp1252"))

    with caplog.at_level("WARNING"):
        result = SpreadsheetParser().parse_spreadsheet(path)

    assert "| 2 | Kahvi | 4,90 € |" in result
    assert "Windows-1252" in caplog.text
    assert "Virtanen" not in caplog.text


@pytest.mark.parametrize(
    ("text", "row"),
    [
        # Each delimiter, with the others inside its cells.
        ("Item,Cost\nRoof; east,450\nGutter; west,12\n", "| 2 | Roof; east | 450 |"),
        ("Item;Cost\nRoof, east;450,5\nGutter, west;12\n", "| 2 | Roof, east | 450,5 |"),
        ("Item\tCost\nRoof, east;\t450\nGutter\t12\n", "| 2 | Roof, east; | 450 |"),
        ("Item|Cost\nRoof, east|450\nGutter|12\n", "| 2 | Roof, east | 450 |"),
        # Quoted cells hold the delimiter.
        ('Item;Cost\n"Roof; east";"1,5"\n', "| 2 | Roof; east | 1,5 |"),
        # A comma in every row's last cell, and none in the header.
        ("Tuote;Hinta\nMaito;1,49\nLeipä;2,10\nKahvi;4,90\n", "| 2 | Maito | 1,49 |"),
        # A tie between ";" and "," goes to ";": Excel's decimal comma.
        ("Maito;1,49\nLeipä;2,10\n", "| 2 | Leipä | 2,10 |"),
        # One column: nothing to split.
        ("Item\nRoof\n", "| 2 | Roof |"),
        # One column of free text with a ";" in some cells: the header does not split.
        ("comment\nhello; world\nfoo; bar\n", "| 2 | hello; world |"),
        ("comment\nhello\tworld\nfoo\tbar\n", "| 2 | hello\tworld |"),
        # An unpadded title row above the header is skipped when reading the delimiter.
        (
            "Sales report\nTuote;Määrä;Hinta\nMaito;2;1,49\nLeipä;1;2,5\n",
            "| 3 | Maito | 2 | 1,49 |",
        ),
        ("Sales report\n\nTuote;Hinta\nMaito;1,49\nLeipä;2,5\n", "| 4 | Maito | 1,49 |"),
    ],
)
def test_csv_delimiter_is_read_from_the_rows(tmp_path, text, row):
    path = tmp_path / "log.csv"
    path.write_text(text, encoding="utf-8", newline="")

    assert row in SpreadsheetParser().parse_spreadsheet(path).splitlines()


def test_csv_delimiter_is_read_from_the_start_of_a_large_file(tmp_path):
    path = tmp_path / "large.csv"
    rows = "".join(f"Item {n};{n},5\n" for n in range(20_000))
    path.write_text("Item;Cost\n" + rows, encoding="utf-8")

    result = SpreadsheetParser().parse_spreadsheet(path).splitlines()

    assert result[2] == "| 2 | Item 0 | 0,5 |"
    assert result[-1] == "| 20001 | Item 19999 | 19999,5 |"


def test_csv_delimiter_and_encoding_can_be_given(tmp_path):
    path = tmp_path / "log.csv"
    path.write_bytes("Tuote,Hinta;Määrä\nMaito,1;2\n".encode("cp1252"))

    parser = SpreadsheetParser(csv_delimiter=";", csv_encoding="cp1252")

    assert parser.parse_spreadsheet(path).splitlines()[2] == "| 2 | Maito,1 | 2 |"


@pytest.mark.parametrize("delimiter", ["", ";;", '"', "\n"])
def test_csv_delimiter_must_be_one_character(delimiter):
    with pytest.raises(ValueError, match="csv_delimiter"):
        SpreadsheetParser(csv_delimiter=delimiter)


def test_csv_in_a_given_encoding_it_is_not_in_raises(tmp_path):
    path = tmp_path / "log.csv"
    path.write_bytes("Tuote;Hinta\nKahvi;4,90 €\n".encode("cp1252"))

    with pytest.raises(ValueError, match=r"log\.csv: the content is not utf-8 text"):
        SpreadsheetParser(csv_encoding="utf-8").parse_spreadsheet(path)
    with pytest.raises(ValueError, match="unknown text encoding"):
        SpreadsheetParser(csv_encoding="no-such-codec").parse_spreadsheet(path)


def test_csv_neither_utf8_nor_cp1252_is_refused_with_the_fix(tmp_path):
    # 0x81 and 0x8D have no character in cp1252, and the bytes are no UTF-8.
    path = tmp_path / "log.csv"
    path.write_bytes(b"Item;Cost\n\x81\x8d;1\n")

    with pytest.raises(ValueError, match="neither UTF-8 nor Windows-1252.*CSV UTF-8"):
        SpreadsheetParser().parse_spreadsheet(path)


def test_a_utf8_csv_with_a_stray_byte_stays_utf8_without_its_byte_order_mark(tmp_path, caplog):
    # The mark says UTF-8: one bad byte must not turn the file into cp1252 mojibake.
    path = tmp_path / "places.csv"
    path.write_bytes(b"\xef\xbb\xbf" + "name;city\nAda;Hämeenlinna\nBo;caf".encode() + b"\xe9\n")

    with caplog.at_level("WARNING"):
        lines = SpreadsheetParser().parse_spreadsheet(path).splitlines()

    assert lines[0] == "| Row | name | city |"
    assert lines[2] == "| 2 | Ada | Hämeenlinna |"
    assert lines[3] == "| 3 | Bo | caf\ufffd |"
    assert "byte order mark" in caplog.text


def test_binary_content_with_nul_bytes_after_the_first_8_kib_is_refused(tmp_path):
    # The type check reads 8 KiB; content past it that is no UTF-8 and holds NUL
    # bytes is binary, not cp1252 text.
    path = tmp_path / "data.csv"
    path.write_bytes(b"a;b\n" * 3000 + b"\x00\x00\xff\x00" + b"c;d\n")

    with pytest.raises(ValueError, match=r"data\.csv: the content holds NUL bytes.*csv_encoding"):
        SpreadsheetParser().parse_spreadsheet(path)


def test_a_utf8_csv_with_nul_bytes_is_still_read(tmp_path):
    # Valid UTF-8 was read before cp1252 existed here; a NUL in it does not change that.
    path = tmp_path / "data.csv"
    path.write_bytes(b"a;b\n" * 3000 + b"c;d\x00\n")

    assert "| 3001 | c | d\x00 |" in SpreadsheetParser().parse_spreadsheet(path)
