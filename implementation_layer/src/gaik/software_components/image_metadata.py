"""Remove the text an image file carries besides its pixels.

An image file can hold text no one sees in the picture: EXIF fields (a
description, a comment, the camera's GPS position), XMP and IPTC packets, PNG
text chunks, JPEG and GIF comments, and data appended after the image. Such text
can carry instructions to a parser, an agent or a model that reads the file, and
personal data the user did not mean to send. ``strip_image_metadata`` returns
the same picture without it.

PNG, JPEG, WebP and GIF are cleaned without decoding the pixels: the file is
walked part by part, a part is kept only when the picture needs it, and kept
parts are copied byte for byte. What stays: a JPEG's JFIF and Adobe segments,
tables, frames and scans (also the later scans of a progressive JPEG), its ICC
colour profile and its orientation (written back as the only EXIF field, so a
phone photo is not turned on its side); a PNG's critical chunks and its
transparency, colour and animation chunks (the ICC profile's name is replaced);
a WebP's image, alpha, animation and ICC chunks (also inside animation frames);
a GIF's frames, graphic control and loop count. Everything else goes, also a
part this module does not know, and anything after the image's end.

TIFF, and a PNG, JPEG, WebP or GIF the walk cannot follow, is re-saved with
Pillow when it is installed: the pixels (turned upright), the compression, the
ICC profile and the resolution are kept, every other tag goes. A file that
cannot be cleaned either way is returned unchanged with nothing reported as
removed, or, with ``strict=True``, refused with ``UnreadableImageError``.

Text drawn in the pixels is not touched: it is the picture. Prompts frame it as
material, never instructions (``source_material.SOURCE_MATERIAL_INSTRUCTION``).
An ICC profile keeps its own description tags, which no model or parser here
reads as text.
"""

from __future__ import annotations

import io
import logging
import struct

logger = logging.getLogger(__name__)

__all__ = ["UnreadableImageError", "strip_image_metadata"]

#: Not decoded past this many pixels in all (``input_limits``' image pixel
#: limit, four times over for a multi-page scan), nor more frames than this.
_MAX_DECODED_PIXELS = 4 * 89_478_485
_MAX_FRAMES = 1000

# The names reported as removed.
EXIF, XMP, IPTC, COMMENT, PNG_TEXT = "EXIF", "XMP", "IPTC", "comment", "PNG text"
OTHER, TRAILING, TIFF_TAGS = "other metadata", "data after the image", "TIFF tags"


class UnreadableImageError(ValueError):
    """An image file that could not be cleaned (``strict=True``)."""


# --- JPEG -----------------------------------------------------------------

_SOI = b"\xff\xd8"
_APP0, _APP1, _APP2, _APP13, _APP14 = 0xE0, 0xE1, 0xE2, 0xED, 0xEE
_SOS, _EOI, _COM = 0xDA, 0xD9, 0xFE
_RST = frozenset(range(0xD0, 0xD8))
#: Tables and frame headers a decoder needs: SOF0-15 (not JPG, 0xC8), DHT, DAC,
#: DQT, DNL, DRI, DHP, EXP.
_JPEG_KEEP = frozenset({*range(0xC0, 0xD0), 0xDB, 0xDC, 0xDD, 0xDE, 0xDF}) - {0xC8}
_ICC = b"ICC_PROFILE\x00"
_EXIF_HEADER = b"Exif\x00\x00"
_ORIENTATION_TAG = 0x0112


def _exif_orientation(payload: bytes) -> int | None:
    """The orientation in an EXIF APP1 payload, or None."""
    tiff = payload[len(_EXIF_HEADER) :]
    if len(tiff) < 8 or tiff[:2] not in (b"II", b"MM"):
        return None
    order = "<" if tiff[:2] == b"II" else ">"
    try:
        (ifd,) = struct.unpack_from(order + "I", tiff, 4)
        (count,) = struct.unpack_from(order + "H", tiff, ifd)
        for n in range(min(count, 1000)):
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
    payload = _EXIF_HEADER + tiff
    return b"\xff" + bytes([_APP1]) + struct.pack(">H", len(payload) + 2) + payload


def _scan_end(data: bytes, i: int) -> int | None:
    """Where the entropy-coded data starting at ``i`` ends: at the first marker
    that is not a restart marker, a stuffed 0xFF00 or a fill byte."""
    n = len(data)
    while True:
        i = data.find(b"\xff", i)
        if i < 0 or i + 1 >= n:
            return None
        after = data[i + 1]
        if after == 0x00 or after in _RST:
            i += 2
        elif after == 0xFF:
            i += 1
        else:
            return i


def _jpeg(data: bytes) -> tuple[bytes, list[str]] | None:
    out = [_SOI]
    removed: list[str] = []
    orientation: int | None = None
    n, i = len(data), 2
    while True:
        if i >= n or data[i] != 0xFF:
            return None
        while i < n and data[i] == 0xFF:  # fill bytes
            i += 1
        if i >= n:
            return None
        marker, i = data[i], i + 1
        if marker == _EOI:
            out.append(b"\xff\xd9")
            if i < n:
                removed.append(TRAILING)
            break
        if marker in _RST or marker == 0x01:
            out.append(bytes([0xFF, marker]))
            continue
        if i + 2 > n:
            return None
        (length,) = struct.unpack_from(">H", data, i)
        end = i + length
        if length < 2 or end > n:
            return None
        segment, payload, i = b"\xff" + data[i - 1 : end], data[i + 2 : end], end
        if marker == _SOS:
            scan_end = _scan_end(data, i)
            if scan_end is None:
                return None
            out += [segment, data[i:scan_end]]
            i = scan_end
        elif (
            marker in _JPEG_KEEP
            or (marker == _APP0 and payload.startswith(b"JFIF\x00"))
            or (marker == _APP14 and payload.startswith(b"Adobe"))
            or (marker == _APP2 and payload.startswith(_ICC))
        ):
            out.append(segment)
        elif marker == _APP1 and payload.startswith(_EXIF_HEADER):
            orientation = _exif_orientation(payload) or orientation
            removed.append(EXIF)
        elif marker == _APP1:
            removed.append(XMP)
        elif marker == _APP13:
            removed.append(IPTC)
        elif marker == _COM:
            removed.append(COMMENT)
        else:
            removed.append(OTHER)
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
_PNG_NAMES = {b"tEXt": PNG_TEXT, b"zTXt": PNG_TEXT, b"iTXt": PNG_TEXT, b"eXIf": EXIF}


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    import zlib

    crc = zlib.crc32(kind + payload)
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def _png(data: bytes) -> tuple[bytes, list[str]] | None:
    out = [_PNG]
    removed: list[str] = []
    i = len(_PNG)
    while True:
        if i + 12 > len(data):
            return None
        length, kind = struct.unpack_from(">I4s", data, i)
        end = i + 12 + length
        if end > len(data):
            return None
        if kind == b"iCCP":
            # The profile's name is free text: a neutral one in its place.
            name_end = data.find(b"\x00", i + 8, i + 8 + min(length, 80))
            if name_end < 0:
                return None
            out.append(_png_chunk(kind, b"ICC profile" + data[name_end : end - 4]))
        elif kind[:1].isupper() or kind in _PNG_KEEP:
            out.append(data[i:end])
        else:
            removed.append(_PNG_NAMES.get(kind, OTHER))
        i = end
        if kind == b"IEND":
            if i < len(data):
                removed.append(TRAILING)
            break
    return b"".join(out), removed


# --- WebP -----------------------------------------------------------------

_WEBP_KEEP = frozenset({b"VP8 ", b"VP8L", b"VP8X", b"ALPH", b"ANIM", b"ANMF", b"ICCP"})
_ANMF_KEEP = frozenset({b"VP8 ", b"VP8L", b"ALPH"})
_ANMF_HEADER = 16
_VP8X_EXIF, _VP8X_XMP = 0x08, 0x04


def _riff_chunks(data: bytes, start: int, end: int) -> list[tuple[bytes, bytes]] | None:
    """The (fourcc, payload) chunks between ``start`` and ``end``."""
    chunks = []
    i = start
    while i < end:
        if i + 8 > end:
            return None
        kind, size = struct.unpack_from("<4sI", data, i)
        if i + 8 + size > end:
            return None
        chunks.append((kind, data[i + 8 : i + 8 + size]))
        i += 8 + size + (size & 1)
    return chunks


def _riff_chunk(kind: bytes, payload: bytes) -> bytes:
    return kind + struct.pack("<I", len(payload)) + payload + (b"\x00" if len(payload) & 1 else b"")


def _webp(data: bytes) -> tuple[bytes, list[str]] | None:
    if len(data) < 12 or data[8:12] != b"WEBP":
        return None
    (size,) = struct.unpack_from("<I", data, 4)
    riff_end = 8 + size
    if riff_end > len(data) or size < 4:
        return None
    chunks = _riff_chunks(data, 12, riff_end)
    if chunks is None:
        return None
    removed = [TRAILING] if len(data) > riff_end else []
    kept: list[bytes] = []
    for kind, payload in chunks:
        if kind not in _WEBP_KEEP:
            removed.append({b"EXIF": EXIF, b"XMP ": XMP}.get(kind, OTHER))
            continue
        if kind == b"VP8X" and payload:
            payload = bytes([payload[0] & ~(_VP8X_EXIF | _VP8X_XMP)]) + payload[1:]
        elif kind == b"ANMF":
            frame = _riff_chunks(payload, _ANMF_HEADER, len(payload))
            if frame is None or len(payload) < _ANMF_HEADER:
                return None
            parts = [_riff_chunk(k, p) for k, p in frame if k in _ANMF_KEEP]
            if len(parts) < len(frame):
                removed.append(OTHER)
            payload = payload[:_ANMF_HEADER] + b"".join(parts)
        kept.append(_riff_chunk(kind, payload))
    body = b"WEBP" + b"".join(kept)
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
                out.append(b"\x3b")
                if i + 1 < len(data):
                    removed.append(TRAILING)
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
                if label == 0xF9:  # graphic control: delay, disposal, transparency
                    out.append(data[start:end])
                elif label == 0xFF and data[i + 2] == 11 and data[i + 3 : i + 14] in _GIF_LOOPING:
                    # Only the loop count (sub-block 1, 3 bytes); any other data goes.
                    loop = data[i + 14 : i + 18]
                    if loop[:2] == b"\x03\x01":
                        out.append(data[i : i + 14] + loop + b"\x00")
                    if end - (i + 14) != (5 if loop[:2] == b"\x03\x01" else 1):
                        removed.append(OTHER)
                else:
                    removed.append({0xFE: COMMENT}.get(label, OTHER))
                i = end
            else:
                return None
    except IndexError:
        return None
    return b"".join(out), removed


# --- Re-saving with Pillow --------------------------------------------------

#: TIFF compressions written back as they were; any other is written as LZW.
_TIFF_COMPRESSIONS = frozenset(
    {"raw", "tiff_lzw", "tiff_adobe_deflate", "tiff_deflate", "packbits", "group3", "group4"}
)


def _resave(data: bytes, tiff: bool) -> tuple[bytes, list[str]] | None:
    """The image saved again by Pillow without its tags, or None."""
    try:
        from PIL import Image, ImageOps, ImageSequence, TiffImagePlugin
    except ImportError:
        return None
    try:
        with Image.open(io.BytesIO(data)) as image:
            frames, pixels = 0, 0
            for frame in ImageSequence.Iterator(image):
                frames += 1
                pixels += frame.size[0] * frame.size[1]
                if frames > _MAX_FRAMES or pixels > _MAX_DECODED_PIXELS:
                    logger.info("An image too large to clean is sent as it is")
                    return None
            image.seek(0)
            out = io.BytesIO()
            if tiff:
                # One page at a time: memory holds one decoded page, not all.
                with TiffImagePlugin.AppendingTiffWriter(out, new=True) as writer:
                    for frame in ImageSequence.Iterator(image):
                        compression = frame.info.get("compression", "raw")
                        if compression not in _TIFF_COMPRESSIONS:
                            compression = "tiff_lzw"
                        options = {"compression": compression}
                        for key in ("dpi", "icc_profile"):
                            if frame.info.get(key):
                                options[key] = frame.info[key]
                        # Turned upright here, so the page needs no orientation tag.
                        page = ImageOps.exif_transpose(frame).copy()
                        page.info = {}  # Pillow writes some info entries back
                        page.save(writer, format="TIFF", **options)
                        writer.newFrame()
                return out.getvalue(), [TIFF_TAGS]
            if frames > 1:
                return None  # an animation the walk could not follow: not re-encoded here
            upright = ImageOps.exif_transpose(image).copy()
            upright.info = {}  # Pillow writes a JPEG's comment back from it
            options = {}
            if image.info.get("icc_profile"):
                options["icc_profile"] = image.info["icc_profile"]
            if image.format == "JPEG":
                options["quality"] = 95
            upright.save(out, format=image.format, **options)
            return out.getvalue(), [OTHER]
    except Exception:  # noqa: BLE001 - not readable here: the caller decides
        return None


def strip_image_metadata(data: bytes, *, strict: bool = False) -> tuple[bytes, tuple[str, ...]]:
    """The image without the text it carries besides its pixels.

    Returns the cleaned bytes and the names of what was removed (``"EXIF"``,
    ``"XMP"``, ``"IPTC"``, ``"comment"``, ``"PNG text"``, ``"TIFF tags"``,
    ``"data after the image"``, ``"other metadata"``), each once. A file that is
    not a PNG, JPEG, WebP, GIF or TIFF comes back unchanged with nothing
    removed. One of those that cannot be cleaned comes back unchanged too, or,
    with ``strict``, raises ``UnreadableImageError``.
    """
    if data.startswith(_SOI):
        result = _jpeg(data)
    elif data.startswith(_PNG):
        result = _png(data)
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        result = _webp(data)
    elif data.startswith((b"GIF87a", b"GIF89a")):
        result = _gif(data)
    elif data.startswith((b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")):
        result = _resave(data, tiff=True)
        if result is None:
            if strict:
                raise UnreadableImageError(
                    "the TIFF image could not be read to remove its metadata"
                )
            logger.warning("A TIFF image is sent with its metadata: it could not be cleaned")
            return data, ()
    else:
        return data, ()
    if result is None:
        result = _resave(data, tiff=False)
    if result is None:
        if strict:
            raise UnreadableImageError("the image could not be read to remove its metadata")
        logger.warning("An image is sent with its metadata: it could not be cleaned")
        return data, ()
    cleaned, removed = result
    names = tuple(dict.fromkeys(removed))
    if names:
        logger.debug("Removed from an image before it is sent: %s", ", ".join(names))
    return cleaned, names
