"""Convert local documents into portable Chat Completions image content."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from gaik.software_components.input_limits import InputLimits

# mimetypes maps .webp only from Python 3.13 on (or via the OS type table).
_IMAGE_MIME_TYPES = {".webp": "image/webp"}

_TEXT_LAYER = (
    "Text layer of {} (the PDF's own characters; copy identifiers, codes and "
    "numbers from here, and read the layout from the image):\n{}"
)


_PAGE_DPI = 150


def build_chat_document_content(
    file_paths: list[Path],
    prompt: str,
    *,
    include_text_layer: bool = False,
    limits: InputLimits | None = None,
) -> list[dict]:
    """Render PDFs as page images and retain native image bytes for vision models.

    PDF-as-file support differs across providers. Page images use the common
    ``image_url`` message format; the selected model still needs vision support.

    ``include_text_layer`` adds each page's own text after its image when the
    page has one. A 150 DPI image alone loses digits of dense identifiers in a
    born-digital PDF (``V-518834`` read as ``V-51884``); the provider's native
    PDF input sends that text too, and an extractor needs the exact characters.

    ``limits`` (default :class:`~gaik.software_components.input_limits.InputLimits`)
    is checked for the pixels of every page image before any page is rendered,
    and for the size and pixels of every image file before it is read.
    """
    limits = limits or InputLimits()
    content: list[dict] = [{"type": "text", "text": prompt}]
    for path in file_paths:
        if path.suffix.lower() == ".pdf":
            try:
                import fitz
            except ImportError as exc:
                raise ImportError(
                    "PDF input through the shared vision client requires PyMuPDF; "
                    "install 'gaik[parser]'."
                ) from exc
            with fitz.open(path) as document:
                for page_number, page in enumerate(document, start=1):
                    limits.check_rendered_page(
                        page, _PAGE_DPI / 72, f"{path.name}, page {page_number}"
                    )
                for page_number, page in enumerate(document, start=1):
                    label = f"{path.name}, page {page_number}"
                    content.append({"type": "text", "text": label})
                    image = page.get_pixmap(dpi=_PAGE_DPI, alpha=False).tobytes("png")
                    content.append(_image_part(image, "image/png"))
                    text = page.get_text("text").strip() if include_text_layer else ""
                    if text:
                        content.append({"type": "text", "text": _TEXT_LAYER.format(label, text)})
        else:
            mime = _IMAGE_MIME_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0]
            if not mime or not mime.startswith("image/"):
                raise ValueError(f"Unsupported vision input type: {path.suffix}")
            limits.check_image_file(path)
            content.append({"type": "text", "text": path.name})
            content.append(_image_part(path.read_bytes(), mime))
    return content


def _image_part(data: bytes, mime: str) -> dict:
    encoded = base64.b64encode(data).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}}
