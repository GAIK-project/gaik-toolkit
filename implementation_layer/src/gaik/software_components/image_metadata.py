"""Remove the text an image file carries besides its pixels.

An image file can hold text no one sees in the picture: EXIF fields (a
description, a comment, the camera's GPS position), XMP and IPTC packets, PNG
text chunks, JPEG and GIF comments. Such text can carry instructions to a model
or an agent that reads the file, and personal data the user did not mean to
send. ``strip_image_metadata`` returns the same picture without it.

The pixels are not decoded or re-encoded for PNG, JPEG, WebP and GIF: the parts
that hold metadata are dropped and the rest is copied byte for byte. What a
picture needs to look right stays: a JPEG's JFIF and Adobe segments, its ICC
colour profile and its orientation (written back as the only EXIF field, so a
phone photo is not turned on its side); a PNG's critical chunks, transparency,
colour and animation chunks; a WebP's image, alpha, animation and ICC chunks;
a GIF's frames and the looping extension. Every other part goes, also one this
module does not know, since a part it does not know can hold text.

TIFF is re-saved with Pillow when it is installed (pixels kept, tags dropped)
and returned unchanged otherwise. BMP holds no metadata. A file that cannot be
parsed is returned unchanged, with nothing reported as removed: the provider
decodes it or refuses it as before.

Text drawn in the pixels is not touched: it is the picture. Prompts frame it as
material, never instructions (``source_material.SOURCE_MATERIAL_INSTRUCTION``).
"""

from __future__ import annotations

import io
import logging
import struct

logger = logging.getLogger(__name__)

__all__ = ["strip_image_metadata"]

# --- JPEG -----------------------------------------------------------------

_SOI = b"\xff\xd8"
_APP0, _APP1, _APP2, _APP14 = 0xE0, 0xE1, 0xE2, 0xEE
_SOS, _EOI, _COM = 0xDA, 0xD9, 0xFE
#: Markers without a length: TEM and the restart markers.
_STANDALONE = frozenset({0x01, *range(0xD0, 0xD8)})
_ICC = b"ICC_PROFILE\x00"
_EXIF = b"Exif\x00\x00"
_ORIENTATION_TAG = 0x0112


def _exif_orientation(payload: bytes) -> int | None:
    """The orientation in an EXIF APP1 payload, or None."""
    tiff = payload[len(_EXIF) :]
    if len(tiff) < 8 or tiff[:2] not in (b"II", b"MM"):
        return None
    order = "<" if tiff[:2] == b"II" else ">"
    try:
        (ifd,) = struct.unpack_from(order + "I", tiff, 4)
        (count,) = struct.unpack_from(order + "H", tiff, ifd)
        for n in range(count):
            tag, kind, _, value = struct.unpack_from(order + "HHI4s", tiff, ifd + 2 + 12 * n)
            if tag == _ORIENTATION_TAG and kind == 3:  # SHORT
                (orientation,) = struct.unpack_from(order + "H", value)
                return orientation if 1 <= orientation <= 8 else None
    except struct.error:
        return None
    return None


def _orientation_segment(orientation: int) -> bytes:
    """An APP1 segment whose EXIF holds the orientation alone."""
    tiff = b"MM\x00\x2a" + struct.pack(">I", 8)
    tiff += struct.pack(">H", 1) + struct.pack(">HHIHH", _ORIENTATION_TAG, 3, 1, orientation, 0)
    tiff += struct.pack(">I", 0)  # no next IFD
    payload = _EXIF + tiff
    return b"\xff" + bytes([_APP1]) + struct.pack(">H", len(payload) + 2) + payload


def _jpeg(data: bytes) -> tuple[bytes, list[str]] | None:
    out = [_SOI]
    removed: list[str] = []
    orientation: int | None = None
    i = 2
    while i < len(data):
        if data[i] != 0xFF:
            return None
        while i < len(data) and data[i] == 0xFF:  # fill bytes
            i += 1
        if i >= len(data):
            return None
        marker = data[i]
        start = i - 1
        i += 1
        if marker in _STANDALONE:
            out.append(data[start:i])
            continue
        if marker == _EOI:
            out.append(data[start:i])
            break
        if i + 2 > len(data):
            return None
        (length,) = struct.unpack_from(">H", data, i)
        end = i + length
        if length < 2 or end > len(data):
            return None
        segment, payload = data[start:end], data[i + 2 : end]
        if marker == _SOS:
            out.append(data[start:])  # the entropy-coded data and everything after it
            break
        i = end
        if marker == _APP0 or marker == _APP14 or (marker == _APP2 and payload.startswith(_ICC)):
            out.append(segment)
        elif 0xE0 <= marker <= 0xEF or marker == _COM:
            if marker == _APP1 and payload.startswith(_EXIF):
                orientation = _exif_orientation(payload) or orientation
                removed.append("EXIF")
            elif marker == _APP1:
                removed.append("XMP")
            elif marker == 0xED:
                removed.append("IPTC")
            elif marker == _COM:
                removed.append("comment")
            else:
                removed.append(f"APP{marker - 0xE0}")
        else:
            out.append(segment)
    else:
        return None
    if orientation and orientation != 1:
        # After SOI and a JFIF APP0, where readers look for it.
        at = 2 if len(out) > 1 and out[1][1:2] == bytes([_APP0]) else 1
        out.insert(at, _orientation_segment(orientation))
    return b"".join(out), removed


# --- PNG ------------------------------------------------------------------

_PNG = b"\x89PNG\r\n\x1a\n"
#: Ancillary chunks a picture needs to look right; every other ancillary chunk
#: (tEXt, zTXt, iTXt, eXIf, tIME and private ones) goes. Critical chunks stay.
_PNG_KEEP = frozenset(
    {
        b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"iCCP", b"sBIT", b"bKGD", b"pHYs",
        b"hIST", b"cICP", b"mDCv", b"cLLi", b"acTL", b"fcTL", b"fdAT",
    }
)  # fmt: skip
_PNG_NAMES = {b"tEXt": "PNG text", b"zTXt": "PNG text", b"iTXt": "PNG text", b"eXIf": "EXIF"}


def _png(data: bytes) -> tuple[bytes, list[str]] | None:
    out = [_PNG]
    removed: list[str] = []
    i = len(_PNG)
    while i < len(data):
        if i + 8 > len(data):
            return None
        length, kind = struct.unpack_from(">I4s", data, i)
        end = i + 12 + length
        if end > len(data):
            return None
        critical = kind[:1].isupper()
        if critical or kind in _PNG_KEEP:
            out.append(data[i:end])
        else:
            removed.append(_PNG_NAMES.get(kind, kind.decode("latin-1")))
        i = end
        if kind == b"IEND":
            break
    else:
        return None
    return b"".join(out), removed


# --- WebP -----------------------------------------------------------------

_WEBP_KEEP = frozenset({b"VP8 ", b"VP8L", b"VP8X", b"ALPH", b"ANIM", b"ANMF", b"ICCP"})
_VP8X_EXIF, _VP8X_XMP = 0x08, 0x04


def _webp(data: bytes) -> tuple[bytes, list[str]] | None:
    if len(data) < 12 or data[8:12] != b"WEBP":
        return None
    chunks: list[bytes] = []
    removed: list[str] = []
    i = 12
    while i + 8 <= len(data):
        kind, size = struct.unpack_from("<4sI", data, i)
        end = i + 8 + size + (size & 1)
        if i + 8 + size > len(data):
            return None
        chunk = data[i : min(end, len(data))]
        if kind in _WEBP_KEEP:
            if kind == b"VP8X" and size >= 1:
                flags = chunk[8] & ~(_VP8X_EXIF | _VP8X_XMP)
                chunk = chunk[:8] + bytes([flags]) + chunk[9:]
            chunks.append(chunk)
        else:
            removed.append({b"EXIF": "EXIF", b"XMP ": "XMP"}.get(kind, kind.decode("latin-1")))
        i = end
    body = b"WEBP" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body, removed


# --- GIF ------------------------------------------------------------------

_GIF_LOOPING = (b"NETSCAPE2.0", b"ANIMEXTS1.0")


def _sub_blocks_end(data: bytes, i: int) -> int:
    """The index after a run of GIF data sub-blocks starting at ``i``."""
    while True:
        size = data[i]
        i += 1 + size
        if size == 0:
            return i


def _gif(data: bytes) -> tuple[bytes, list[str]] | None:
    if len(data) < 13 or data[:6] not in (b"GIF87a", b"GIF89a"):
        return None
    removed: list[str] = []
    try:
        i = 13
        if data[10] & 0x80:  # global colour table
            i += 3 * (2 ** ((data[10] & 0x07) + 1))
        out = [data[:i]]
        while True:
            block = data[i]
            if block == 0x3B:  # trailer
                out.append(data[i : i + 1])
                break
            if block == 0x2C:  # image descriptor
                start = i
                packed = data[i + 9]
                i += 10
                if packed & 0x80:  # local colour table
                    i += 3 * (2 ** ((packed & 0x07) + 1))
                i = _sub_blocks_end(data, i + 1)  # after the LZW minimum code size
                out.append(data[start:i])
            elif block == 0x21:  # extension
                label, start = data[i + 1], i
                end = _sub_blocks_end(data, i + 2)
                application = data[i + 3 : i + 14] if label == 0xFF else b""
                if label == 0xF9 or application in _GIF_LOOPING:
                    out.append(data[start:end])
                else:
                    removed.append(
                        {0xFE: "comment", 0x01: "plain text", 0xFF: "application data"}.get(
                            label, f"extension {label:#04x}"
                        )
                    )
                i = end
            else:
                return None
    except IndexError:
        return None
    return b"".join(out), removed


# --- TIFF -----------------------------------------------------------------

_TIFF_KEEP_INFO = frozenset({"icc_profile", "dpi"})
#: Not decoded past this (``input_limits``' image pixel limit, Pillow's own).
_TIFF_MAX_PIXELS = 89_478_485


def _tiff(data: bytes) -> tuple[bytes, list[str]] | None:
    try:
        from PIL import Image, ImageSequence
    except ImportError:
        logger.info("Pillow is not installed: a TIFF image is sent with its metadata")
        return None
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if width * height > _TIFF_MAX_PIXELS:
                return None
            # Copies are plain images: Pillow writes a TiffImageFile's XMP, IPTC
            # and Photoshop tags back, a copy has none, and only the info the
            # pixels need is kept.
            frames = []
            for frame in ImageSequence.Iterator(image):
                copy = frame.copy()
                copy.info = {k: v for k, v in frame.info.items() if k in _TIFF_KEEP_INFO}
                frames.append(copy)
        out = io.BytesIO()
        frames[0].save(out, format="TIFF", save_all=True, append_images=frames[1:])
    except Exception:  # noqa: BLE001 - unreadable here: sent as it is, as before
        return None
    return out.getvalue(), ["TIFF tags"]


def strip_image_metadata(data: bytes) -> tuple[bytes, tuple[str, ...]]:
    """The image without the text it carries besides its pixels.

    Returns the cleaned bytes and the names of what was removed (``"EXIF"``,
    ``"XMP"``, ``"comment"``, ``"PNG text"``, ...), each once, in the order
    found; empty when nothing was, or when the file is not one of PNG, JPEG,
    WebP, GIF or TIFF or cannot be parsed (then the bytes come back unchanged).
    """
    if data.startswith(_SOI):
        result = _jpeg(data)
    elif data.startswith(_PNG):
        result = _png(data)
    elif data.startswith(b"RIFF"):
        result = _webp(data)
    elif data.startswith((b"GIF87a", b"GIF89a")):
        result = _gif(data)
    elif data.startswith((b"II*\x00", b"MM\x00*")):
        result = _tiff(data)
    else:
        result = None
    if result is None:
        return data, ()
    cleaned, removed = result
    names = tuple(dict.fromkeys(removed))
    if names:
        logger.debug("Removed from an image before it is sent: %s", ", ".join(names))
    return cleaned, names
