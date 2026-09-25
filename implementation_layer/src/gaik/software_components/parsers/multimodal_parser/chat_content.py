"""Convert local documents into portable Chat Completions image content."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path


def build_chat_document_content(file_paths: list[Path], prompt: str) -> list[dict]:
    """Render PDFs as page images and retain native image bytes for vision models.

    PDF-as-file support differs across providers. Page images use the common
    ``image_url`` message format; the selected model still needs vision support.
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
                    content.append({"type": "text", "text": f"{path.name}, page {page_number}"})
                    image = page.get_pixmap(dpi=150, alpha=False).tobytes("png")
                    content.append(_image_part(image, "image/png"))
        else:
            mime = mimetypes.guess_type(path.name)[0]
            if not mime or not mime.startswith("image/"):
                raise ValueError(f"Unsupported vision input type: {path.suffix}")
            content.append({"type": "text", "text": path.name})
            content.append(_image_part(path.read_bytes(), mime))
    return content


def _image_part(data: bytes, mime: str) -> dict:
    encoded = base64.b64encode(data).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}}
