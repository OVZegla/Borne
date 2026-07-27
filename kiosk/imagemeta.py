"""Lecture des dimensions d'une image directement dans ses entetes.

Evite toute dependance a Pillow : on lit juste ce qu'il faut d'octets.
"""

from __future__ import annotations

import struct


def dimensions(data: bytes) -> tuple[int, int] | None:
    """Retourne (largeur, hauteur) ou None si le format n'est pas reconnu."""
    for reader in (_png, _gif, _bmp, _webp, _jpeg):
        try:
            size = reader(data)
        except (struct.error, IndexError, ValueError):
            continue
        if size:
            return size
    return None


def _png(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def _gif(data: bytes) -> tuple[int, int] | None:
    if not data.startswith((b"GIF87a", b"GIF89a")):
        return None
    width, height = struct.unpack("<HH", data[6:10])
    return width, height


def _bmp(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(b"BM"):
        return None
    width, height = struct.unpack("<ii", data[18:26])
    return abs(width), abs(height)


def _webp(data: bytes) -> tuple[int, int] | None:
    if not (data.startswith(b"RIFF") and data[8:12] == b"WEBP"):
        return None
    chunk = data[12:16]
    if chunk == b"VP8X":
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
        return width, height
    if chunk == b"VP8L":
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8 ":
        width, height = struct.unpack("<HH", data[26:30])
        return width & 0x3FFF, height & 0x3FFF
    return None


# Marqueurs JPEG portant les dimensions (SOF0..SOF15, hors marqueurs non-SOF).
_SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def _jpeg(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(b"\xff\xd8"):
        return None
    offset = 2
    end = len(data)
    while offset < end - 9:
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            offset += 2
            continue
        if marker == 0xDA:  # debut des donnees compressees
            return None
        length = struct.unpack(">H", data[offset + 2:offset + 4])[0]
        if marker in _SOF_MARKERS:
            height, width = struct.unpack(">HH", data[offset + 5:offset + 9])
            return width, height
        offset += 2 + length
    return None
