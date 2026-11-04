"""Convert local documents into portable Chat Completions image content."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

# mimetypes maps .webp only from Python 3.13 on (or via the OS type table).
_IMAGE_MIME_TYPES = {".webp": "image/webp"}

_TEXT_LAYER = (
    "Text layer of {} (the PDF's own characters; copy identifiers, codes and "
    "numbers from here, and read the layout from the image):\n{}"
)


def build_chat_document_content(
    file_paths: list[Path], prompt: str, *, include_text_layer: bool = False
) -> list[dict]:
    """Render PDFs as page images and retain native image bytes for vision models.

    PDF-as-file support differs across providers. Page images use the common
    ``image_url`` message format; the selected model still needs vision support.

    ``include_text_layer`` adds each page's own text after its image when the
    page has one. A 150 DPI image alone loses digits of dense identifiers in a
    born-digital PDF (``V-518834`` read as ``V-51884``); the provider's native
    PDF input sends that text too, and an extractor needs the exact characters.
    """
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
                    label = f"{path.name}, page {page_number}"
                    content.append({"type": "text", "text": label})
                    image = page.get_pixmap(dpi=150, alpha=False).tobytes("png")
                    content.append(_image_part(image, "image/png"))
                    text = page.get_text("text").strip() if include_text_layer else ""
                    if text:
                        content.append({"type": "text", "text": _TEXT_LAYER.format(label, text)})
        else:
            mime = _IMAGE_MIME_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0]
            if not mime or not mime.startswith("image/"):
                raise ValueError(f"Unsupported vision input type: {path.suffix}")
            content.append({"type": "text", "text": path.name})
            content.append(_image_part(path.read_bytes(), mime))
    return content


def _image_part(data: bytes, mime: str) -> dict:
    encoded = base64.b64encode(data).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}}
