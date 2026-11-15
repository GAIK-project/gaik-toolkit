"""The DOCX export converts the report's Markdown file and reads nothing else."""

import zipfile

import pytest
from gaik.software_components import _pandoc


def test_the_export_asks_pandoc_for_the_image_filter_and_no_raw_blocks(tmp_path, monkeypatch):
    pypandoc = pytest.importorskip("pypandoc")
    calls = []

    def record(source, to, **kwargs):
        [arg] = kwargs["extra_args"]
        filter_path = arg.removeprefix("--lua-filter=")
        with open(filter_path, encoding="utf-8") as f:
            calls.append((source, to, kwargs, f.read()))

    monkeypatch.setattr(pypandoc, "convert_file", record)
    md = tmp_path / "report.md"
    md.write_text("# Report\n", encoding="utf-8")

    out = _pandoc.markdown_file_to_docx(md, tmp_path / "report.docx")

    assert out == tmp_path / "report.docx"
    [(source, to, kwargs, lua)] = calls
    assert (source, to) == (str(md), "docx")
    assert "--sandbox" not in kwargs["extra_args"]
    assert lua == _pandoc.IMAGES_AS_ALT_TEXT
    for extension in ("-raw_html", "-raw_tex", "-raw_attribute"):
        assert extension in kwargs["format"]


def _pandoc_or_skip():
    pypandoc = pytest.importorskip("pypandoc")
    try:
        pypandoc.get_pandoc_version()
    except OSError:
        pytest.skip("Pandoc binary not installed")
    return pypandoc


def test_a_picture_next_to_the_report_stays_out_of_the_docx(tmp_path):
    pypandoc = _pandoc_or_skip()
    outside = tmp_path / "outside"
    outside.mkdir()
    picture = outside / "picture.png"
    # A 1x1 PNG.
    picture.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
            "1f15c4890000000d49444154789c6360000002000100e221bc330000000049454e44ae426082"
        )
    )
    report = tmp_path / "report"
    report.mkdir()
    md = report / "report.md"
    md.write_text(
        f"# Report\n\nBefore.\n\n![a picture]({picture})\n\nAfter.\n",
        encoding="utf-8",
    )

    out = _pandoc.markdown_file_to_docx(md, report / "report.docx")

    with zipfile.ZipFile(out) as docx:
        assert not [n for n in docx.namelist() if n.startswith("word/media/")]
    text = pypandoc.convert_file(str(out), "plain")
    assert "Before." in text and "After." in text
    assert "a picture" in text


def test_an_image_address_becomes_its_alt_text(tmp_path):
    pypandoc = _pandoc_or_skip()
    md = tmp_path / "report.md"
    # Port 9 on the loopback address: nothing answers there.
    md.write_text(
        "# Report\n\nSee ![the chart](http://127.0.0.1:9/chart.png) here.\n",
        encoding="utf-8",
    )

    out = _pandoc.markdown_file_to_docx(md, tmp_path / "report.docx")

    with zipfile.ZipFile(out) as docx:
        assert not [n for n in docx.namelist() if n.startswith("word/media/")]
    assert "See the chart here." in " ".join(pypandoc.convert_file(str(out), "plain").split())


def test_a_raw_block_in_the_markdown_is_kept_as_text(tmp_path):
    _pandoc_or_skip()
    md = tmp_path / "report.md"
    md.write_text(
        "# Report\n\n```{=openxml}\n<w:p><w:r><w:t>INSERTED</w:t></w:r></w:p>\n```\n\n"
        "<b>bold?</b>\n",
        encoding="utf-8",
    )

    out = _pandoc.markdown_file_to_docx(md, tmp_path / "report.docx")

    with zipfile.ZipFile(out) as docx:
        body = docx.read("word/document.xml").decode("utf-8")
    # The block is shown as its source text, not merged into the document XML.
    assert "&lt;w:t&gt;INSERTED&lt;/w:t&gt;" in body
    assert "<w:t>INSERTED</w:t>" not in body
    assert "&lt;b&gt;bold?&lt;/b&gt;" in body
