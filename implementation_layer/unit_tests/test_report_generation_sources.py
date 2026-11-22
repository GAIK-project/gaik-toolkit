"""The multi-source report generator reads each kind of source as it is.

Offline: the parsers that would call a model are replaced by fakes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from gaik.software_modules.multi_source_report_generator import MultiSourceReportGenerator
from gaik.software_modules.multi_source_report_generator import pipeline as msrg

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _gen() -> MultiSourceReportGenerator:
    return MultiSourceReportGenerator(api_config={"use_azure": False, "api_key": "x", "model": "m"})


def _evidence(path: Path, **options) -> str:
    return _gen()._extract_content(
        path,
        source_type=msrg._EXT_TO_TYPE[path.suffix.lower()],
        parser_choice=options.get("parser_choice", "auto"),
        parser_options=options.get("parser_options", {}),
        transcriber_options={},
        image_options=options.get("image_options", {}),
    )


# -- .xls ----------------------------------------------------------------------


@pytest.mark.parametrize("as_folder", [False, True], ids=["file", "in-a-folder"])
def test_an_xls_source_is_refused_before_any_source_is_read(tmp_path, monkeypatch, as_folder):
    (tmp_path / "a_notes.txt").write_text("Notes.", encoding="utf-8")
    (tmp_path / "b_meeting.mp3").write_bytes(b"ID3")
    (tmp_path / "c_costs.xls").write_bytes(b"\xd0\xcf\x11\xe0")
    read: list[str] = []
    monkeypatch.setattr(
        MultiSourceReportGenerator,
        "_extract_content",
        lambda self, path, **kwargs: read.append(path.name) or "text",
    )
    inputs = (
        [tmp_path]
        if as_folder
        else [tmp_path / "a_notes.txt", tmp_path / "b_meeting.mp3", tmp_path / "c_costs.xls"]
    )
    with pytest.raises(ValueError, match=r"c_costs\.xls: .*save it as \.xlsx"):
        _gen().run(input_paths=inputs, sections=[{"title": "A", "instructions": "x"}])
    assert read == []


def test_xls_is_no_longer_a_supported_extension():
    assert ".xls" not in msrg.SUPPORTED_EXTENSIONS
    assert ".xlsx" in msrg.SUPPORTED_EXTENSIONS


# -- docling ---------------------------------------------------------------------


def test_docling_evidence_is_the_parsed_markdown(tmp_path, monkeypatch):
    import gaik.software_components.parsers as parsers

    class FakeDocling:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def parse_document(self, file_path):
            return {
                "file_path": file_path,
                "file_name": Path(file_path).name,
                "text_content": "# Report\n\nThe roof is old.",
                "parsing_method": "docling",
            }

    monkeypatch.setattr(parsers, "DoclingParser", FakeDocling, raising=False)
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    text = _evidence(pdf, parser_choice="docling", parser_options={"ctor": {"enable_ocr": False}})
    assert text == "# Report\n\nThe roof is old."


# -- DOCX ------------------------------------------------------------------------


def test_a_docx_keeps_document_order_headings_and_empty_cells(tmp_path):
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_heading("Costs", level=1)
    document.add_paragraph("The table lists the repairs.")
    table = document.add_table(rows=3, cols=3)
    for r, row in enumerate([["Item", "Year", "Cost"], ["Roof", "", "4500"], ["Wall", "2019", ""]]):
        for c, value in enumerate(row):
            table.cell(r, c).text = value
    document.add_heading("Findings", level=1)
    document.add_paragraph("The roof leaks.")
    path = tmp_path / "survey.docx"
    document.save(path)

    text = _evidence(path)
    assert "# Costs" in text and "# Findings" in text
    assert text.index("# Costs") < text.index("| Roof") < text.index("# Findings")
    roof = next(line for line in text.splitlines() if line.startswith("| Roof"))
    # The empty Year cell keeps its column, so 4500 stays under Cost.
    assert [cell.strip() for cell in roof.strip("|").split("|")] == ["Roof", "", "4500"]


# -- TIFF and BMP ------------------------------------------------------------------


@pytest.fixture
def vision_calls(monkeypatch):
    import gaik.software_components.parsers as parsers

    calls: list[bytes] = []

    class FakeVision:
        def __init__(self, config, **kwargs):
            self.kwargs = kwargs

        def convert_image(self, image_path):
            data = Path(image_path).read_bytes()
            calls.append(data)
            return f"page text {len(calls)}"

    monkeypatch.setattr(parsers, "VisionParser", FakeVision, raising=False)
    return calls


def _image(path: Path, fmt: str, frames: int = 1, mode: str = "RGB") -> Path:
    image_module = pytest.importorskip("PIL.Image")
    images = [image_module.new(mode, (40, 30), "white") for _ in range(frames)]
    images[0].save(path, format=fmt, save_all=frames > 1, append_images=images[1:])
    return path


@pytest.mark.parametrize(
    ("name", "fmt"), [("scan.tif", "TIFF"), ("scan.tiff", "TIFF"), ("x.bmp", "BMP")]
)
def test_tiff_and_bmp_reach_the_model_as_png(tmp_path, vision_calls, name, fmt):
    path = _image(tmp_path / name, fmt)
    assert _evidence(path) == "page text 1"
    assert len(vision_calls) == 1 and vision_calls[0].startswith(PNG_SIGNATURE)


def test_a_multi_page_tiff_is_read_page_by_page(tmp_path, vision_calls):
    path = _image(tmp_path / "scan.tif", "TIFF", frames=3, mode="CMYK")
    text = _evidence(path)
    assert text.startswith("[Page 1]\n\npage text 1") and "[Page 3]\n\npage text 3" in text
    assert len(vision_calls) == 3 and all(c.startswith(PNG_SIGNATURE) for c in vision_calls)


def test_a_tiff_over_the_page_limit_is_refused_before_a_model_call(tmp_path, vision_calls):
    from gaik.software_components.input_limits import InputLimitError, InputLimits

    path = _image(tmp_path / "scan.tif", "TIFF", frames=3)
    generator = MultiSourceReportGenerator(
        api_config={"use_azure": False, "api_key": "x", "model": "m"},
        limits=InputLimits(max_pages=2),
    )
    with pytest.raises(InputLimitError):
        generator._parse_image(path, image_options={})
    assert vision_calls == []


def test_a_png_is_sent_as_it_is(tmp_path, vision_calls):
    path = _image(tmp_path / "photo.png", "PNG")
    _evidence(path)
    assert vision_calls == [path.read_bytes()]


def test_structured_image_mode_gets_png_files_too(tmp_path, monkeypatch):
    import gaik.software_components.vision_extractor as vision_extractor

    seen: list[bytes] = []

    class FakeExtractor:
        def __init__(self, **kwargs):
            pass

        def extract(self, *, file_paths, user_requirements):
            seen.extend(Path(p).read_bytes()[:8] for p in file_paths)
            return type("Result", (), {"data": {"text": "scan"}})()

    monkeypatch.setattr(vision_extractor, "VisionExtractor", FakeExtractor, raising=False)
    path = _image(tmp_path / "scan.bmp", "BMP")
    assert "scan" in _evidence(path, image_options={"mode": "structured"})
    assert seen == [PNG_SIGNATURE]


# -- table cells -------------------------------------------------------------------


def test_csv_cells_with_a_pipe_or_a_line_break_stay_in_their_column(tmp_path):
    path = tmp_path / "log.csv"
    path.write_text(
        'Part,Note,Year\nRoof,"Repaired 2019 | partial",2019\nWall,"two\nlines",2020\n',
        encoding="utf-8",
    )
    table = msrg._csv_to_markdown(path)
    lines = table.splitlines()
    assert len(lines) == 4  # header, rule, two rows: no row is split
    assert lines[2] == "| Roof | Repaired 2019 \\| partial | 2019 |"
    assert lines[3] == "| Wall | two lines | 2020 |"


def test_xlsx_cells_are_escaped_like_csv_cells(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Part", "Note"])
    sheet.append(["Roof", "a | b\nc"])
    path = tmp_path / "log.xlsx"
    workbook.save(path)
    assert "| Roof | a \\| b c |" in msrg._xlsx_to_markdown(path)
