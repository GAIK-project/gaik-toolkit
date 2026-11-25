"""Remove the text an image file carries besides its pixels.

An image file can hold text no one sees in the picture: EXIF fields (a
description, a comment, the camera's GPS position), XMP and IPTC packets, PNG
text chunks, JPEG and GIF comments, and data appended after the image. Such text
can carry instructions to a parser, an agent or a model that reads the file, and
personal data the user did not mean to send. ``strip_image_metadata`` returns
the same picture without it.

PNG, JPEG and WebP are cleaned without decoding the pixels: the file is walked
part by part, a part is kept only when the picture needs it, and kept parts are
copied byte for byte. What stays: a JPEG's JFIF and Adobe segments, tables,
frames and scans (also the later scans of a progressive JPEG), its ICC colour
profile; a PNG's critical chunks and its transparency, colour and animation
chunks (the ICC profile's name is replaced); a WebP's image, alpha, animation
and ICC chunks (also inside animation frames). The orientation of all three is
written back as the only EXIF field, so a phone photo is not turned on its side.
Everything else goes, also a part this module does not know, and anything after
the image's end.

A GIF is rebuilt instead, because its parts can hold bytes a reader skips: the
screen, frame and graphic-control fields and the loop count are written again
from their values, each frame's pixels are decoded and encoded again with
Pillow, and colour-table entries no pixel uses are written as zero. Frames,
timing, disposal, transparency and the palette stay; a GIF that cannot be
rebuilt, or without Pillow, is not cleaned.

TIFF, BMP, and a PNG, JPEG or WebP the walk cannot follow, is re-saved with Pillow
when it is installed: the pixels (turned upright), the compression, the ICC
profile and the resolution are kept, every other tag goes. A file that cannot be
cleaned either way is returned unchanged with nothing reported as removed, or,
with ``strict=True``, refused with ``UnreadableImageError``.

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

#: Not decoded past this many pixels for one picture or page (``input_limits``'
#: image pixel limit), four times that for all pages of a scan, nor more pages.
_MAX_IMAGE_PIXELS = 89_478_485
_MAX_DECODED_PIXELS = 4 * _MAX_IMAGE_PIXELS
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


def _tiff_orientation(tiff: bytes) -> int | None:
    """The orientation in an EXIF block (a TIFF header and its first IFD), or None."""
    if tiff.startswith(_EXIF_HEADER):
        tiff = tiff[len(_EXIF_HEADER) :]
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


def _orientation_exif(orientation: int) -> bytes:
    """An EXIF block (without the ``Exif`` header) holding the orientation alone."""
    tiff = b"MM\x00\x2a" + struct.pack(">I", 8)
    tiff += struct.pack(">H", 1) + struct.pack(">HHIHH", _ORIENTATION_TAG, 3, 1, orientation, 0)
    return tiff + struct.pack(">I", 0)  # no next IFD


def _segment(marker: int, payload: bytes) -> bytes:
    return b"\xff" + bytes([marker]) + struct.pack(">H", len(payload) + 2) + payload


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
        elif marker == _APP0 and payload.startswith(b"JFIF\x00") and len(payload) >= 14:
            # The JFIF header alone: version, density; no thumbnail, nothing after.
            out.append(_segment(_APP0, payload[:12] + b"\x00\x00"))
            if len(payload) > 14:
                removed.append(OTHER)
        elif marker == _APP14 and payload.startswith(b"Adobe") and len(payload) >= 12:
            # Version, flags and colour transform: 12 bytes; nothing after.
            out.append(_segment(_APP14, payload[:12]))
            if len(payload) > 12:
                removed.append(OTHER)
        elif marker in _JPEG_KEEP or (marker == _APP2 and payload.startswith(_ICC)):
            out.append(segment)
        elif marker == _APP1 and payload.startswith(_EXIF_HEADER):
            orientation = orientation or _tiff_orientation(payload)
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
        out.insert(at, _segment(_APP1, _EXIF_HEADER + _orientation_exif(orientation)))
    return b"".join(out), removed


# --- PNG ------------------------------------------------------------------

_PNG = b"\x89PNG\r\n\x1a\n"
#: The chunks a picture needs, critical and ancillary; every other ancillary
#: chunk (tEXt, zTXt, iTXt, eXIf, tIME and private ones) goes, and so does a
#: kept chunk longer than its kind holds.
#: Each with the most bytes it holds (None: image or profile data, any length).
_PNG_KEEP = {
    b"IHDR": 13, b"PLTE": 768, b"IDAT": None, b"IEND": 0,
    b"tRNS": 256, b"gAMA": 4, b"cHRM": 32, b"sRGB": 1, b"iCCP": None, b"sBIT": 4,
    b"bKGD": 6, b"pHYs": 9, b"hIST": 512, b"cICP": 4, b"mDCv": 24, b"cLLi": 8,
    b"acTL": 8, b"fcTL": 26, b"fdAT": None,
}  # fmt: skip
_PNG_NAMES = {b"tEXt": PNG_TEXT, b"zTXt": PNG_TEXT, b"iTXt": PNG_TEXT, b"eXIf": EXIF}


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    import zlib

    crc = zlib.crc32(kind + payload)
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def _png(data: bytes) -> tuple[bytes, list[str]] | None:
    out = [_PNG]
    removed: list[str] = []
    orientation: int | None = None
    first_idat: int | None = None
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
        elif kind == b"IDAT" and first_idat is None:
            first_idat = len(out)
            out.append(data[i:end])
        elif kind in _PNG_KEEP and (_PNG_KEEP[kind] is None or length <= _PNG_KEEP[kind]):
            out.append(data[i:end])
        elif kind[:1].isupper():
            return None  # a critical chunk not known here: not walked, saved again
        else:
            if kind == b"eXIf":
                orientation = orientation or _tiff_orientation(data[i + 8 : end - 4])
            removed.append(_PNG_NAMES.get(kind, OTHER))
        i = end
        if kind == b"IEND":
            if i < len(data):
                removed.append(TRAILING)
            break
    if orientation and orientation != 1 and first_idat is not None:
        # The orientation alone, before the image data, where readers look for it.
        out.insert(first_idat, _png_chunk(b"eXIf", _orientation_exif(orientation)))
    return b"".join(out), removed


# --- WebP -----------------------------------------------------------------

_WEBP_KEEP = frozenset({b"VP8 ", b"VP8L", b"VP8X", b"ALPH", b"ANIM", b"ANMF", b"ICCP"})
_ANMF_KEEP = frozenset({b"VP8 ", b"VP8L", b"ALPH"})
_ANMF_HEADER = 16
_VP8X_EXIF, _VP8X_XMP, _VP8X_ALPHA = 0x08, 0x04, 0x10
_VP8X_SIZE = 10


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


def _webp_vp8x(chunks: list[tuple[bytes, bytes]]) -> bytes | None:
    """A VP8X chunk for a simple WebP (one VP8 or VP8L image), or None."""
    images = [(kind, payload) for kind, payload in chunks if kind in _WEBP_KEEP]
    if len(images) != 1 or images[0][0] not in (b"VP8 ", b"VP8L"):
        return None
    kind, image = images[0]
    flags = 0
    if kind == b"VP8L":  # signature, then 14 bits each of width-1 and height-1, alpha
        if len(image) < 5 or image[0] != 0x2F:
            return None
        (bits,) = struct.unpack_from("<I", image, 1)
        width, height = (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        flags = _VP8X_ALPHA if bits & (1 << 28) else 0
    else:  # a key frame: frame tag, start code, 14-bit width and height
        if len(image) < 10 or image[3:6] != b"\x9d\x01\x2a":
            return None
        width = struct.unpack_from("<H", image, 6)[0] & 0x3FFF
        height = struct.unpack_from("<H", image, 8)[0] & 0x3FFF
    if not width or not height:
        return None
    size = (width - 1).to_bytes(3, "little") + (height - 1).to_bytes(3, "little")
    return _riff_chunk(b"VP8X", bytes([flags, 0, 0, 0]) + size)


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
    orientation: int | None = None
    for kind, payload in chunks:
        if kind not in _WEBP_KEEP:
            if kind == b"EXIF":
                orientation = orientation or _tiff_orientation(payload)
            removed.append({b"EXIF": EXIF, b"XMP ": XMP}.get(kind, OTHER))
            continue
        if kind == b"VP8X":
            if len(payload) != _VP8X_SIZE:
                return None
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
    if not kept:
        return None
    if orientation and orientation != 1:
        # The orientation alone, flagged in VP8X (added for a simple WebP).
        if kept[0][:4] != b"VP8X":
            vp8x = _webp_vp8x(chunks)
            if vp8x is None:
                return None
            kept.insert(0, vp8x)
        kept[0] = kept[0][:8] + bytes([kept[0][8] | _VP8X_EXIF]) + kept[0][9:]
        kept.append(_riff_chunk(b"EXIF", _orientation_exif(orientation)))
    body = b"WEBP" + b"".join(kept)
    return b"RIFF" + struct.pack("<I", len(body)) + body, removed


# --- GIF ------------------------------------------------------------------
#
# A GIF is rebuilt, not copied: each part the picture needs is written again
# from the values read out of it, and each frame's pixels are decoded and
# encoded again (with Pillow), so no byte of the original file reaches the
# output as it was. Colour-table entries that no pixel, background or
# transparency uses are written as zero.

_GIF_LOOPING = (b"NETSCAPE2.0", b"ANIMEXTS1.0")


def _sub_blocks(data: bytes, i: int) -> tuple[list[bytes], int]:
    """The GIF data sub-blocks starting at ``i`` and the index after them."""
    blocks = []
    while True:
        size = data[i]
        if i + 1 + size > len(data):
            raise IndexError
        if size == 0:
            return blocks, i + 1
        blocks.append(data[i + 1 : i + 1 + size])
        i += 1 + size


def _gif_table(data: bytes, i: int, packed: int) -> tuple[bytearray | None, int]:
    """The colour table a packed field announces at ``i``, and the index after it."""
    if not packed & 0x80:
        return None, i
    size = 3 << ((packed & 0x07) + 1)
    if i + size > len(data):
        raise IndexError
    return bytearray(data[i : i + size]), i + size


class _GifFrame:
    def __init__(self, control, left, top, width, height, interlaced, table, lzw):
        self.control = control  # (disposal and transparency flags, delay, index) or None
        self.left, self.top, self.width, self.height = left, top, width, height
        self.interlaced, self.table, self.lzw = interlaced, table, lzw
        self.used: set[int] = set()


def _gif_indices(frame: _GifFrame, image_module):
    """A frame's colour indices as an "L" image, decoded by Pillow from a one-frame GIF."""
    w, h = frame.width, frame.height
    lone = (
        b"GIF89a" + struct.pack("<HHBBB", w, h, 0, 0, 0)  # no colour table: read as indices
        + b"\x2c" + struct.pack("<HHHHB", 0, 0, w, h, 0x40 if frame.interlaced else 0)
        + frame.lzw + b"\x3b"
    )  # fmt: skip
    with image_module.open(io.BytesIO(lone)) as image:
        if image.mode != "L" or image.size != (w, h):
            raise ValueError("unexpected GIF frame")
        image.load()
        return image.copy()


def _gif_lzw(indices, gif_module) -> bytes:
    """The LZW minimum code size and image sub-blocks Pillow writes for the indices."""
    written = b"".join(gif_module.getdata(indices))
    if written[:1] != b"\x2c" or written[9] & 0x80:
        raise ValueError("unexpected GIF encoder output")
    return written[10:]


def _gif(data: bytes) -> tuple[bytes, list[str]] | None:
    if len(data) < 13 or data[:6] not in (b"GIF87a", b"GIF89a"):
        return None
    try:
        from PIL import GifImagePlugin, Image
    except ImportError:
        return None
    removed: list[str] = []
    frames: list[_GifFrame] = []
    loop: int | None = None
    control = None
    try:
        width, height, screen, background, _ = struct.unpack_from("<HHBBB", data, 6)
        palette, i = _gif_table(data, 13, screen)
        while True:
            if i == len(data) and frames:
                break  # no trailer: the frames before the end are kept
            block = data[i]
            if block == 0x3B:  # trailer
                if i + 1 < len(data):
                    removed.append(TRAILING)
                break
            if block == 0x2C:  # image descriptor
                left, top, w, h, packed = struct.unpack_from("<HHHHB", data, i + 1)
                table, i = _gif_table(data, i + 10, packed)
                start = i  # the LZW minimum code size, then the image sub-blocks
                _, i = _sub_blocks(data, i + 1)
                frames.append(
                    _GifFrame(control, left, top, w, h, packed & 0x40, table, data[start:i])
                )
                control = None
                if len(frames) > _MAX_FRAMES:
                    logger.info("A GIF with too many frames to clean")
                    return None
            elif block == 0x21:  # extension
                label = data[i + 1]
                blocks, i = _sub_blocks(data, i + 2)
                if label == 0xF9 and blocks and len(blocks[0]) == 4:
                    # Disposal, transparency flag, delay and transparent index.
                    packed, delay, index = struct.unpack("<BHB", blocks[0])
                    control = (packed & 0x1D, delay, index if packed & 0x01 else 0)
                    if len(blocks) > 1 or packed & ~0x1D:
                        removed.append(OTHER)
                elif (
                    label == 0xFF
                    and blocks
                    and blocks[0] in _GIF_LOOPING
                    and loop is None
                    and len(blocks) > 1
                    and len(blocks[1]) == 3
                    and blocks[1][0] == 1
                ):
                    (loop,) = struct.unpack_from("<H", blocks[1], 1)
                    if len(blocks) > 2:
                        removed.append(OTHER)
                elif label == 0xF9:
                    return None  # a graphic control not read here
                else:
                    removed.append({0xFE: COMMENT}.get(label, OTHER))
            else:
                return None
    except (IndexError, struct.error):
        return None
    if not frames:
        return None
    if any(f.width * f.height > _MAX_IMAGE_PIXELS for f in frames) or (
        sum(f.width * f.height for f in frames) > _MAX_DECODED_PIXELS
    ):
        logger.info("A GIF too large to clean")
        return None

    global_used: set[int] = {background}
    lzw: list[bytes] = []
    try:
        for frame in frames:
            indices = _gif_indices(frame, Image)
            used = {n for n, count in enumerate(indices.histogram()) if count}
            if frame.control and frame.control[0] & 0x01:
                used.add(frame.control[2])
            if frame.table is None:
                global_used |= used
            frame.used = used
            lzw.append(_gif_lzw(indices, GifImagePlugin))
    except Exception:  # noqa: BLE001 - not readable here: the caller decides
        return None

    def zeroed(table: bytearray, used) -> bytes:
        kept = bytearray(len(table))
        for n in used:
            kept[3 * n : 3 * n + 3] = table[3 * n : 3 * n + 3]
        if kept != table:
            removed.append(OTHER)
        return bytes(kept)

    out = [
        b"GIF89a",
        struct.pack("<HHBBB", width, height, screen, background if palette is not None else 0, 0),
    ]
    if palette is not None:
        out.append(zeroed(palette, global_used))
    if loop is not None:
        out.append(b"\x21\xff\x0bNETSCAPE2.0\x03\x01" + struct.pack("<H", loop) + b"\x00")
    for frame, image_data in zip(frames, lzw):
        if frame.control is not None:
            out.append(b"\x21\xf9\x04" + struct.pack("<BHB", *frame.control) + b"\x00")
        # The local table's flag and size; not interlaced, as Pillow writes the pixels.
        packed = 0
        if frame.table is not None:
            packed = 0x80 | ((len(frame.table) // 3).bit_length() - 2)
        place = struct.pack("<HHHH", frame.left, frame.top, frame.width, frame.height)
        out.append(b"\x2c" + place + bytes([packed]))
        if frame.table is not None:
            out.append(zeroed(frame.table, frame.used))
        out.append(image_data)
    out.append(b"\x3b")
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
                size = frame.size[0] * frame.size[1]
                pixels += size
                if frames > _MAX_FRAMES or size > _MAX_IMAGE_PIXELS or pixels > _MAX_DECODED_PIXELS:
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
            options = {
                key: image.info[key]
                for key in ("icc_profile", "transparency")
                if image.info.get(key) is not None
            }
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
    not a PNG, JPEG, WebP, GIF, TIFF or BMP comes back unchanged with nothing
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
    elif data.startswith(b"BM"):
        # BMP: a V5 header can embed a profile, and bytes can sit between the
        # headers and the pixels or after them. Saved again, it holds pixels only.
        result = _resave(data, tiff=False)
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
    if result is None and not data.startswith(b"GIF"):
        # A GIF is rebuilt by Pillow or not at all (see the GIF part above).
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
