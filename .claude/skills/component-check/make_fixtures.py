"""Render the synthetic text invoices in fixtures/ as a PDF with a text layer and a PNG scan.

Every fixture is made up: the company names, the business ID (its check digit is wrong
on purpose) and the amounts. Run again only when a .txt fixture changes:

    uv run python .claude/skills/component-check/make_fixtures.py
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF, installed with gaik's parser extras

FIXTURES = Path(__file__).resolve().parent / "fixtures"
RENDERED = ("invoice-fi",)
FONT_SIZE = 10.5
LINE_HEIGHT = 15
MARGIN = 56
PNG_DPI = 150


def render(stem: str) -> None:
    text = (FIXTURES / f"{stem}.txt").read_text(encoding="utf-8")
    document = fitz.open()
    page = document.new_page(width=595, height=842)  # A4 in points
    y = MARGIN
    for line in text.splitlines():
        # Courier keeps the table columns where the .txt has them.
        page.insert_text((MARGIN, y), line, fontname="cour", fontsize=FONT_SIZE)
        y += LINE_HEIGHT
    document.set_metadata({"title": f"Synthetic {stem}", "creator": "component-check"})
    document.save(FIXTURES / f"{stem}.pdf", garbage=4, deflate=True, no_new_id=True)
    page.get_pixmap(dpi=PNG_DPI).save(FIXTURES / f"{stem}.png")
    # The text layer must hold what the .txt says, or the vision cases test the renderer.
    written = fitz.open(FIXTURES / f"{stem}.pdf")[0].get_text()
    for token in ("INV-2026-0042", "Esimerkki Oy", "Tiivistesarja", "551,57"):
        if token not in written:
            raise SystemExit(f"{stem}.pdf lost {token!r} in its text layer")


def main() -> None:
    for stem in RENDERED:
        render(stem)
        print(f"wrote fixtures/{stem}.pdf and fixtures/{stem}.png")


if __name__ == "__main__":
    main()
