"""Validation shared by adapters accepting canonical Chat Completions image parts."""

from __future__ import annotations

import base64
import binascii


def image_data(part: dict) -> tuple[str, bytes]:
    """Decode an inline image without fetching a caller-supplied URL."""
    image = part.get("image_url")
    url = image.get("url") if isinstance(image, dict) else image
    if not isinstance(url, str) or not url.startswith("data:image/"):
        raise ValueError("Image content requires a base64 data:image/... URL")
    header, separator, data = url.partition(",")
    if not separator or not header.endswith(";base64"):
        raise ValueError("Image content requires a base64 data:image/... URL")
    mime_type = header[5:-7]
    if mime_type not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
        raise ValueError("Unsupported inline image MIME type")
    try:
        decoded = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Image content contains invalid base64") from exc
    if not decoded:
        raise ValueError("Image content cannot be empty")
    return mime_type, decoded
