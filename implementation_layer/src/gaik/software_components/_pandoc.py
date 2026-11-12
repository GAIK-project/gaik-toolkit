"""Markdown to DOCX through Pandoc, reading nothing but the Markdown file itself.

The report components write Markdown whose text comes from a model and from the
sources it was given. Pandoc converts it in sandbox mode (Pandoc 2.15 or later):
it reads no other file and opens no address, so an image reference becomes its
alt text. Raw HTML, raw TeX and ``{=format}`` blocks are read as plain text, so
nothing passes into the DOCX unconverted.
"""

from __future__ import annotations

from pathlib import Path

# Markdown with the raw passthrough extensions turned off.
MARKDOWN_INPUT = "markdown-raw_html-raw_tex-raw_attribute"
SANDBOX_ARGS = ["--sandbox"]


def markdown_file_to_docx(md_path: str | Path, docx_path: str | Path) -> Path:
    """Convert ``md_path`` to ``docx_path`` and return ``docx_path`` as a Path.

    Needs ``pypandoc`` and Pandoc 2.15 or later; an older Pandoc rejects
    ``--sandbox`` and the conversion fails instead of running without it.
    """
    import pypandoc

    out = Path(docx_path)
    pypandoc.convert_file(
        str(md_path),
        "docx",
        format=MARKDOWN_INPUT,
        outputfile=str(out),
        extra_args=list(SANDBOX_ARGS),
    )
    return out
