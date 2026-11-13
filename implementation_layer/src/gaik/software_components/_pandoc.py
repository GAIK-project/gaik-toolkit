"""Markdown to DOCX through Pandoc, reading nothing but the Markdown file itself.

The report components write Markdown whose text comes from a model and from the
sources it was given. Two settings keep that text from pulling anything else into
the DOCX:

- A Lua filter replaces every image with its alt text before the DOCX writer
  runs, so Pandoc reads no image file and opens no address.
- Raw HTML, raw TeX and ``{=format}`` blocks are read as plain text, so nothing
  passes into the DOCX unconverted.

Pandoc's ``--sandbox`` is not used: a Pandoc that keeps its data files on disk,
such as the Debian and Ubuntu packages, cannot write DOCX in sandbox mode.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

# Markdown with the raw passthrough extensions turned off.
MARKDOWN_INPUT = "markdown-raw_html-raw_tex-raw_attribute"

# Every image becomes its alt text, before the writer could read or fetch it.
IMAGES_AS_ALT_TEXT = "function Image(el)\n  return el.caption\nend\n"


def markdown_file_to_docx(md_path: str | Path, docx_path: str | Path) -> Path:
    """Convert ``md_path`` to ``docx_path`` and return ``docx_path`` as a Path.

    Needs ``pypandoc`` and the Pandoc binary; a distribution package works.
    """
    import pypandoc

    out = Path(docx_path)
    with tempfile.TemporaryDirectory(prefix="gaik-pandoc-") as tmp:
        lua_filter = Path(tmp) / "images_as_alt_text.lua"
        lua_filter.write_text(IMAGES_AS_ALT_TEXT, encoding="utf-8")
        pypandoc.convert_file(
            str(md_path),
            "docx",
            format=MARKDOWN_INPUT,
            outputfile=str(out),
            extra_args=[f"--lua-filter={lua_filter}"],
        )
    return out
