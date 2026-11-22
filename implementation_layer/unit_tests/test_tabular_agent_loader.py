"""Unit tests for tabular_agent file loading and spreadsheet clean-up.

These build their own fixtures in ``tmp_path`` and never call an LLM: layout
inference is exercised through an injected callback, so the deterministic tiers
and the LLM tier can both be tested offline.
"""

import pytest

pytest.importorskip("duckdb")
pytest.importorskip("openpyxl")

import duckdb  # noqa: E402
from gaik.software_components.tabular_agent.loader import (  # noqa: E402
    TableLoadError,
    _detect_header_row,
    _drop_shape_outliers,
    _looks_messy,
    _read_grid,
    _trim_grid,
    load_sources,
    normalize_sources,
    sanitize_identifier,
)
from gaik.software_components.tabular_agent.models import SheetLayout  # noqa: E402
from openpyxl import Workbook  # noqa: E402

CLEAN_ROWS = [
    ("North", "Q1", 120, 14400.0),
    ("South", "Q1", 90, 10800.0),
    ("East", "Q1", 210, 25200.0),
    ("West", "Q1", 60, 7200.0),
]


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    yield connection
    connection.close()


def _load(con, path, **kwargs):
    """Load one file and return ``{table_name: source}``."""
    return load_sources(con, normalize_sources(path), **kwargs)


# ---------------------------------------------------------------- identifiers


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Sales Report", "sales_report"),
        ("Revenue (EUR)", "revenue_eur"),
        ("2026 totals", "t_2026_totals"),
        ("  ", "table"),
        ("Myynti/Alue", "myynti_alue"),
    ],
)
def test_sanitize_identifier(raw, expected):
    assert sanitize_identifier(raw) == expected


# ------------------------------------------------------------------ CSV paths


def test_loads_plain_csv(con, tmp_path):
    path = tmp_path / "sales.csv"
    path.write_text(
        "region,quarter,units,revenue\n"
        + "\n".join(f"{r},{q},{u},{v}" for r, q, u, v in CLEAN_ROWS)
        + "\n",
        encoding="utf-8",
    )
    tables = _load(con, path)
    assert list(tables) == ["sales"]
    assert con.execute("SELECT count(*) FROM sales").fetchone()[0] == 4


def test_loads_semicolon_csv_with_bom_and_comma_decimals(con, tmp_path):
    """Nordic exports: ';' separator, ',' decimal mark, UTF-8 BOM."""
    path = tmp_path / "myynti.csv"
    path.write_text(
        "region;quarter;units;revenue\n"
        + "\n".join(f"{r};{q};{u};{v:.2f}".replace(".", ",") for r, q, u, v in CLEAN_ROWS)
        + "\n",
        encoding="utf-8-sig",
    )
    _load(con, path)
    types = {r[0]: r[1] for r in con.execute("DESCRIBE myynti").fetchall()}
    assert types["revenue"] == "DOUBLE", "comma-decimals must be usable in SUM()"
    assert con.execute("SELECT sum(revenue) FROM myynti").fetchone()[0] == pytest.approx(57600.0)
    assert con.execute("SELECT count(*) FROM myynti").fetchone()[0] == 4


def test_free_text_with_commas_is_not_converted_to_numbers(con, tmp_path):
    """The decimal repair must only fire when every value is a number."""
    path = tmp_path / "notes.csv"
    path.write_text("id;comment\n1;hello, world\n2;3,5 was the score\n", encoding="utf-8")
    _load(con, path)
    types = {r[0]: r[1] for r in con.execute("DESCRIBE notes").fetchall()}
    assert types["comment"].startswith("VARCHAR")


def _column(con, table, column):
    """``(type, values in row order)`` of one column."""
    types = {r[0]: r[1] for r in con.execute(f'DESCRIBE "{table}"').fetchall()}
    values = [r[0] for r in con.execute(f'SELECT "{column}" FROM "{table}" ORDER BY id').fetchall()]
    return types[column], values


def test_us_thousands_commas_are_not_read_as_decimals(con, tmp_path, caplog):
    """1,200 is as likely to be twelve hundred as one point two: the column stays text."""
    import logging

    path = tmp_path / "orders.csv"
    path.write_text('id,Matti Virtanen\n1,"1,200"\n2,"3,450"\n3,"12,000"\n', encoding="utf-8")
    with caplog.at_level(logging.INFO, logger="gaik.software_components.tabular_agent"):
        _load(con, path)
    data_type, values = _column(con, "orders", "Matti Virtanen")
    assert data_type == "VARCHAR"
    assert values == ["1,200", "3,450", "12,000"]
    # The log line says how many columns, not which: a header can name a person.
    assert "Left 1 column(s) as text" in caplog.text
    assert "Virtanen" not in caplog.text


@pytest.mark.parametrize(
    "space",
    [" ", " ", " "],
    ids=["space", "no-break space", "narrow no-break space"],
)
def test_space_grouped_comma_decimals_are_converted(con, tmp_path, space):
    path = tmp_path / "myynti.csv"
    rows = ["1 234,56", "987,5", "12 345 678,90", "-1 000,25"]
    path.write_text(
        "id;summa\n" + "".join(f"{i};{v.replace(' ', space)}\n" for i, v in enumerate(rows)),
        encoding="utf-8",
    )
    _load(con, path)
    data_type, values = _column(con, "myynti", "summa")
    assert data_type == "DOUBLE"
    assert values == pytest.approx([1234.56, 987.5, 12345678.9, -1000.25])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # One value that cannot be thousands grouping decides the whole column.
        (["1,200", "3,5"], [1.2, 3.5]),
        (["1,200", "1.234,56"], [1.2, 1234.56]),
        (["1,200", "0,250"], [1.2, 0.25]),
        (["1,200", "1234,567"], [1.2, 1234.567]),
        (["1,200", "1 234,5"], [1.2, 1234.5]),
        ([" 12,5 ", "3,25"], [12.5, 3.25]),
        (["+1,5", "-0,25", "+1 234,5"], [1.5, -0.25, 1234.5]),
        # Every value could be thousands grouping, or one can only be: text.
        (["1,200", "-3,450"], None),
        (["1,200", "1,234,567"], None),
        (["1,200", "1,200.50"], None),
        # Not every value is a number: text.
        (["1,5", "n/a"], None),
        # A unit stays with the value rather than being dropped from it.
        (["12,5 %", "3,25 %"], None),
        (["1 234,56 €", "987,50 €"], None),
    ],
)
def test_a_column_is_read_as_comma_decimals_only_when_it_cannot_be_thousands(
    con, tmp_path, raw, expected
):
    path = tmp_path / "mixed.csv"
    path.write_text(
        "id;value\n" + "".join(f'{i};"{v}"\n' for i, v in enumerate(raw)), encoding="utf-8"
    )
    _load(con, path)
    data_type, values = _column(con, "mixed", "value")
    if expected is None:
        assert data_type == "VARCHAR"
        assert values == raw
    else:
        assert data_type == "DOUBLE"
        assert values == pytest.approx(expected)


def test_excel_text_cells_get_the_same_number_handling(con, tmp_path):
    path = tmp_path / "book.xlsx"
    _write_clean_xlsx(
        path,
        {
            "Sheet1": [
                ("id", "summa", "us_amount"),
                (1, "1 234,56", "1,200"),
                (2, "987,5", "12,000"),
            ]
        },
    )
    _load(con, path)
    assert _column(con, "book", "summa") == ("DOUBLE", pytest.approx([1234.56, 987.5]))
    assert _column(con, "book", "us_amount") == ("VARCHAR", ["1,200", "12,000"])


def test_a_column_name_with_a_double_quote_is_loaded_and_profiled(con, tmp_path):
    from gaik.software_components.tabular_agent.profiling import profile_tables

    path = tmp_path / "pipes.csv"
    path.write_text('id;5" pipe;price\n1;yes;1,5\n2;no;2,25\n', encoding="utf-8")

    tables = _load(con, path)
    schema = profile_tables(con, tables)

    [table] = schema.tables
    assert table.row_count == 2
    assert [column.name for column in table.columns] == ["id", '5" pipe', "price"]
    # The comma decimals are still repaired next to the oddly named column.
    assert con.execute('SELECT sum(price) FROM "pipes"').fetchone()[0] == 3.75


def test_a_failed_profile_is_logged_without_the_table_names(con, caplog):
    """A table is named after its file or sheet, which can carry personal data."""
    import logging

    from gaik.software_components.tabular_agent.profiling import profile_tables

    # DuckDB's error names the missing table and suggests the existing one.
    con.execute("CREATE TABLE matti_virtanen_lab_2 (a INTEGER)")
    tables = {"matti_virtanen_lab": "Matti_Virtanen_lab.csv", "matti_virtanen_lab_2": "x.csv"}
    with caplog.at_level(logging.WARNING, logger="gaik.software_components.tabular_agent"):
        schema = profile_tables(con, tables)

    [record] = [r for r in caplog.records if "Could not profile" in r.getMessage()]
    message = record.getMessage().lower()
    assert "virtanen" not in message
    assert "CatalogException" in record.getMessage(), "the cause is kept"
    # The caller still gets the table, with its name, and the profile of the other one.
    assert [t.name for t in schema.tables] == list(tables)
    assert schema.tables[1].row_count == 0


def test_rejects_unsupported_extension(tmp_path):
    path = tmp_path / "notes.pdf"
    path.write_bytes(b"%PDF-1.4")
    with pytest.raises(TableLoadError, match="Unsupported file type"):
        normalize_sources(path)


def test_rejects_missing_file(tmp_path):
    with pytest.raises(TableLoadError, match="File not found"):
        normalize_sources(tmp_path / "nope.csv")


def test_mapping_source_names_the_table(con, tmp_path):
    path = tmp_path / "raw_export_2026.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    tables = load_sources(con, normalize_sources({"myynti": path}))
    assert list(tables) == ["myynti"]


def test_two_files_with_the_same_stem_get_unique_names(con, tmp_path):
    first = tmp_path / "a" / "data.csv"
    second = tmp_path / "b" / "data.csv"
    for path in (first, second):
        path.parent.mkdir(parents=True)
        path.write_text("x\n1\n", encoding="utf-8")
    tables = load_sources(con, normalize_sources([first, second]))
    assert list(tables) == ["data", "data_2"]


# ---------------------------------------------------------------- Excel paths


def _write_clean_xlsx(path, sheets):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for title, rows in sheets.items():
        sheet = workbook.create_sheet(title)
        for row in rows:
            sheet.append(list(row))
    workbook.save(path)


def test_loads_one_table_per_sheet(con, tmp_path):
    path = tmp_path / "book.xlsx"
    _write_clean_xlsx(
        path,
        {
            "Sales": [("region", "units")] + [(r, u) for r, _, u, _ in CLEAN_ROWS],
            "Headcount": [("region", "employees"), ("North", 12), ("South", 9)],
        },
    )
    tables = _load(con, path)
    assert set(tables) == {"sales", "headcount"}
    assert con.execute("SELECT count(*) FROM sales").fetchone()[0] == 4
    assert con.execute("SELECT count(*) FROM headcount").fetchone()[0] == 2


def test_single_sheet_workbook_is_named_after_the_file(con, tmp_path):
    path = tmp_path / "quarterly.xlsx"
    _write_clean_xlsx(path, {"Sheet1": [("a", "b"), (1, 2)]})
    assert list(_load(con, path)) == ["quarterly"]


def test_blank_leading_rows_and_columns_are_dropped(con, tmp_path):
    path = tmp_path / "padded.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append([])
    sheet.append([None, None, "region", "units"])
    sheet.append([None, None, "North", 120])
    sheet.append([None, None, "South", 90])
    workbook.save(path)
    _load(con, path)
    columns = [r[0] for r in con.execute("DESCRIBE padded").fetchall()]
    assert columns == ["region", "units"]
    assert con.execute("SELECT count(*) FROM padded").fetchone()[0] == 2


def test_unnamed_columns_get_generated_names(con, tmp_path):
    path = tmp_path / "partial.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["region", None, "units"])
    sheet.append(["North", "x", 120])
    sheet.append(["South", "y", 90])
    workbook.save(path)
    _load(con, path)
    columns = [r[0] for r in con.execute("DESCRIBE partial").fetchall()]
    assert columns[0] == "region"
    assert columns[1].startswith("column_")


_HEADER = ["Määrä", "Hinta (€)", "Région", '5" pipe']


def test_excel_headers_are_named_as_the_same_csv_header_is(con, tmp_path):
    """Non-ASCII letters, signs and case survive the Excel path, as they do for a CSV."""
    xlsx, csv_path = tmp_path / "kirja.xlsx", tmp_path / "kirja_csv.csv"
    _write_clean_xlsx(xlsx, {"Sheet1": [_HEADER, (3, 2.5, "Nord", 1), (4, 1.5, "Sud", 2)]})
    csv_path.write_text(
        ",".join('"' + h.replace('"', '""') + '"' for h in _HEADER) + "\n3,2.5,Nord,1\n",
        encoding="utf-8",
    )
    _load(con, xlsx)
    _load(con, csv_path)

    def names(table):
        return [r[0] for r in con.execute(f'DESCRIBE "{table}"').fetchall()]

    assert names("kirja") == _HEADER
    assert names("kirja") == names("kirja_csv")


def test_excel_header_repeats_line_breaks_and_numbers_get_usable_names(con, tmp_path):
    path = tmp_path / "report.xlsx"
    rows = [("Region", "region", "Sales\nEUR", 2024, None), ("North", "N", 10, 11, 12)]
    _write_clean_xlsx(path, {"Sheet1": rows + [("South", "S", 20, 21, 22)]})
    _load(con, path)
    columns = [r[0] for r in con.execute("DESCRIBE report").fetchall()]
    # DuckDB's names are case-insensitive, so the repeat needs a suffix.
    assert columns == ["Region", "region_2", "Sales EUR", "2024", "column_5"]
    assert con.execute("SELECT count(*) FROM report").fetchone()[0] == 2


def test_excel_headers_differing_in_a_non_ascii_letter_case_are_two_columns(con, tmp_path):
    """DuckDB folds the case of ASCII letters only, so Å and å are two names, as in a CSV."""
    path = tmp_path / "letters.xlsx"
    _write_clean_xlsx(path, {"Sheet1": [("Å", "å", "Ä", "a", "A"), (1, 2, 3, 4, 5)]})
    _load(con, path)
    assert [r[0] for r in con.execute("DESCRIBE letters").fetchall()] == ["Å", "å", "Ä", "a", "A_2"]


def test_semicolons_in_excel_headers_and_cells_do_not_split_columns(con, tmp_path):
    path = tmp_path / "notes.xlsx"
    rows = [("Notes;A", "Notes;B"), ("x;y", "z;w"), ("a;b", "c;d")]
    _write_clean_xlsx(path, {"Sheet1": rows})
    _load(con, path)
    assert [r[0] for r in con.execute("DESCRIBE notes").fetchall()] == ["Notes;A", "Notes;B"]
    assert con.execute("SELECT * FROM notes").fetchall() == [("x;y", "z;w"), ("a;b", "c;d")]


def test_an_excel_header_of_years_is_not_read_back_as_a_data_row(con, tmp_path):
    path = tmp_path / "years.xlsx"
    _write_clean_xlsx(path, {"Sheet1": [(2024, 2025), (1, 2), (3, 4)]})
    _load(con, path)
    assert [r[0] for r in con.execute("DESCRIBE years").fetchall()] == ["2024", "2025"]
    assert con.execute('SELECT sum("2025") FROM years').fetchone()[0] == 6


def test_non_ascii_excel_columns_pass_the_validator_and_run(con, tmp_path):
    from gaik.software_components.tabular_agent.sql_safety import validate_read_only

    path = tmp_path / "kirja.xlsx"
    _write_clean_xlsx(path, {"Sheet1": [_HEADER, (3, 2.5, "Nord", 1), (4, 1.5, "Sud", 2)]})
    _load(con, path)
    for sql, expected in (
        ('SELECT sum(Määrä), sum("Hinta (€)") FROM kirja', (7, 4.0)),
        ('SELECT sum("Määrä"), sum("hinta (€)") FROM kirja WHERE Région <> \'x\'', (7, 4.0)),
        ('SELECT sum(k."5"" pipe") FROM kirja AS k', (3,)),
    ):
        checked = validate_read_only(sql, allowed_tables=["kirja"])
        assert con.execute(checked).fetchone() == expected


def test_the_schema_text_quotes_the_names_sql_cannot_read_bare(con, tmp_path):
    from gaik.software_components.tabular_agent.profiling import profile_tables

    path = tmp_path / "kirja.xlsx"
    rows = [_HEADER + ["unit_price", "2024"], (3, 2.5, "Nord", 1, 9, 1), (4, 1.5, "Sud", 2, 8, 2)]
    _write_clean_xlsx(path, {"Sheet1": rows})
    text = profile_tables(con, _load(con, path)).to_prompt_text()
    for quoted in ('"Määrä" BIGINT', '"Hinta (€)" DOUBLE', '"Région" VARCHAR', '"5"" pipe"'):
        assert f"\n  {quoted}" in text
    assert '"2024" BIGINT' in text
    assert "\n  unit_price BIGINT" in text


# Header words DuckDB reserves, or that the validator's parser reads as syntax.
_KEYWORD_HEADER = ["select", "From", "order", "limit", "Group", "if", "drop", "where"]


def test_the_schema_text_quotes_keywords_and_the_quoted_names_run(con, tmp_path):
    from gaik.software_components.tabular_agent.profiling import profile_tables
    from gaik.software_components.tabular_agent.sql_safety import validate_read_only

    path = tmp_path / "order.csv"
    path.write_text(
        ",".join(_KEYWORD_HEADER + ["name", "year"]) + "\n" + ",".join(["1"] * 10) + "\n",
        encoding="utf-8",
    )
    tables = _load(con, path)
    text = profile_tables(con, tables).to_prompt_text()
    # The table is named after the file, and "order" is a keyword too.
    assert text.startswith('TABLE "order"  -- from order.csv')
    for name in _KEYWORD_HEADER:
        assert f'\n  "{name}" BIGINT' in text
        # Written the way the schema shows it, the name passes the validator and runs.
        sql = f'SELECT sum("{name}") FROM "order" WHERE "{name}" > 0 GROUP BY "{name}"'
        assert con.execute(validate_read_only(sql, allowed_tables=list(tables))).fetchone() == (1,)
    # Ordinary words that are not reserved stay bare.
    assert "\n  name BIGINT" in text
    assert "\n  year BIGINT" in text


@pytest.mark.parametrize("name", ["from", "limit", "select", "where", "if", "drop"])
def test_these_keywords_fail_bare_so_the_quotes_are_needed(con, name):
    """Guards the test above: each name in it does break a query written bare."""
    from gaik.software_components.tabular_agent.sql_safety import (
        UnsafeSQLError,
        validate_read_only,
    )

    con.execute(f'CREATE TABLE t ("{name}" INTEGER, other INTEGER)')
    con.execute("INSERT INTO t VALUES (1, 1)")
    failures = 0
    for sql in (
        f"SELECT {name} FROM t",
        f"SELECT sum({name}) FROM t WHERE {name} > 0",
        f"SELECT {name} FROM t GROUP BY {name}, other",
    ):
        try:
            if con.execute(validate_read_only(sql)).fetchall() != [(1,)]:
                failures += 1
        except (UnsafeSQLError, duckdb.Error):
            failures += 1
    assert failures


def test_empty_sheets_are_skipped(con, tmp_path):
    path = tmp_path / "mixed.xlsx"
    _write_clean_xlsx(path, {"Empty": [], "Real": [("a",), (1,)]})
    assert list(_load(con, path)) == ["real"]


def test_workbook_with_no_usable_sheet_raises(con, tmp_path):
    path = tmp_path / "blank.xlsx"
    _write_clean_xlsx(path, {"Empty": []})
    with pytest.raises(TableLoadError, match="No usable sheets"):
        _load(con, path)


# ------------------------------------------------------- messy-sheet handling


def _messy_workbook(path):
    """A human-facing report: title rows, subtotals, and a trailing note block."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Report"
    sheet.append(["ACME -- Quarterly Sales"])
    sheet.append(["Figures in EUR"])
    sheet.append([])
    sheet.append(["Region", "Quarter", "Units", "Revenue"])
    for region, _, units, revenue in CLEAN_ROWS:
        for quarter in ("Q1", "Q2", "Q3"):
            sheet.append([region, quarter, units, revenue])
        sheet.append([f"{region} subtotal", None, units * 3, revenue * 3])
    sheet.append([])
    sheet.append(["Notes:"])
    sheet.append(["Unaudited."])
    workbook.save(path)


def _grid(path, sheet_name):
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        return _trim_grid(_read_grid(workbook[sheet_name]))
    finally:
        workbook.close()


def test_header_row_found_below_title_rows(tmp_path):
    path = tmp_path / "messy.xlsx"
    _messy_workbook(path)
    grid = _grid(path, "Report")
    # Row 2 after the blank spacer row is trimmed away.
    assert _detect_header_row(grid) == 2


def test_messy_sheet_is_flagged_and_clean_sheet_is_not(tmp_path):
    messy = tmp_path / "messy.xlsx"
    _messy_workbook(messy)
    messy_grid = _grid(messy, "Report")
    assert _looks_messy(messy_grid, _detect_header_row(messy_grid)) is True

    clean = tmp_path / "clean.xlsx"
    _write_clean_xlsx(
        clean, {"Sales": [("region", "units")] + [(r, u) for r, _, u, _ in CLEAN_ROWS]}
    )
    clean_grid = _grid(clean, "Sales")
    assert _looks_messy(clean_grid, _detect_header_row(clean_grid)) is False


def test_subtotal_rows_are_dropped_structurally():
    """A subtotal blanks the label columns but keeps the numbers."""
    rows = []
    for region in ("North", "South", "East"):
        rows += [
            [region, "Q1", 120, 14400.0],
            [region, "Q2", 90, 10800.0],
            [region, "Q3", 60, 7200.0],
        ]
        rows.append([f"{region} subtotal", None, 270, 32400.0])
    kept = _drop_shape_outliers(rows)
    assert len(kept) == 9
    assert all(row[1] is not None for row in kept)


def test_note_rows_are_dropped():
    """A trailing note fills almost nothing, whatever its columns are."""
    rows = [["North", "Q1", 120, 14400.0] for _ in range(9)]
    rows += [["Notes:", None, None, None], ["Unaudited.", None, None, None]]
    assert len(_drop_shape_outliers(rows)) == 9


def test_rows_missing_a_numeric_value_are_kept():
    """A real observation with a gap in a measure is not a subtotal."""
    rows = [["North", "Q1", 120, 14400.0] for _ in range(9)]
    rows.append(["South", "Q1", 90, None])
    assert len(_drop_shape_outliers(rows)) == 10


def test_outlier_filter_gives_up_without_a_dominant_shape():
    rows = [["a", None, None], [None, "b", None], [None, None, "c"]]
    assert _drop_shape_outliers(rows) == rows


def test_layout_inference_callback_trims_trailing_notes(con, tmp_path):
    """The LLM tier is exercised through an injected callback -- no API call."""
    path = tmp_path / "messy.xlsx"
    _messy_workbook(path)
    calls = []

    def fake_infer(sheet_label, grid_text):
        calls.append(sheet_label)
        assert "row 0" in grid_text
        return SheetLayout(
            header_row=2,
            data_start_row=3,
            data_end_row=18,  # stop before the notes block
            skip_columns=[],
            reasoning="test",
        )

    _load(con, path, layout_inference="auto", infer_layout=fake_infer)
    assert calls, "a messy sheet must trigger layout inference"
    regions = [r[0] for r in con.execute("SELECT region FROM messy").fetchall()]
    assert "Notes:" not in regions
    assert not any("subtotal" in str(r) for r in regions)


def test_clean_sheet_does_not_trigger_layout_inference(con, tmp_path):
    """Tidy files must cost zero extra tokens."""
    path = tmp_path / "clean.xlsx"
    _write_clean_xlsx(
        path, {"Sales": [("region", "units")] + [(r, u) for r, _, u, _ in CLEAN_ROWS]}
    )
    calls = []

    def fake_infer(sheet_label, grid_text):
        calls.append(sheet_label)
        raise AssertionError("should not be called for a clean sheet")

    _load(con, path, layout_inference="auto", infer_layout=fake_infer)
    assert calls == []


def test_never_mode_skips_inference_even_when_messy(con, tmp_path):
    path = tmp_path / "messy.xlsx"
    _messy_workbook(path)

    def fake_infer(sheet_label, grid_text):
        raise AssertionError("should not be called in 'never' mode")

    _load(con, path, layout_inference="never", infer_layout=fake_infer)
    assert con.execute("SELECT count(*) FROM messy").fetchone()[0] > 0


def test_unusable_inferred_layout_falls_back_to_heuristic(con, tmp_path):
    path = tmp_path / "messy.xlsx"
    _messy_workbook(path)

    def bad_infer(sheet_label, grid_text):
        return SheetLayout(
            header_row=999,
            data_start_row=1000,
            data_end_row=None,
            skip_columns=[],
            reasoning="nonsense",
        )

    _load(con, path, layout_inference="auto", infer_layout=bad_infer)
    assert con.execute("SELECT count(*) FROM messy").fetchone()[0] > 0


def test_inference_failure_falls_back_to_heuristic(con, tmp_path):
    path = tmp_path / "messy.xlsx"
    _messy_workbook(path)

    def failing_infer(sheet_label, grid_text):
        raise RuntimeError("LLM unavailable")

    _load(con, path, layout_inference="auto", infer_layout=failing_infer)
    assert con.execute("SELECT count(*) FROM messy").fetchone()[0] > 0
