#!/usr/bin/env python3
"""Generate assets/avatar.png — a pixel-art lunch train in UIUC colors.

Stdlib-only PNG writer: 16x16 sprite scaled to 512x512. Upload the result as
the GitHub machine account's profile picture so the Slack cards get a face.
"""

import struct
import zlib
from pathlib import Path

SCALE = 32
PALETTE = {
    ".": (0x13, 0x29, 0x4B),  # Illini navy (background)
    "o": (0xFF, 0x5F, 0x05),  # Illini orange (train body)
    "d": (0xC7, 0x4A, 0x04),  # dark orange (stack, chassis)
    "w": (0xFF, 0xFF, 0xFF),  # white (steam, windows)
    "k": (0x10, 0x14, 0x18),  # wheels
    "g": (0x8D, 0x99, 0xAE),  # track
    "y": (0xFF, 0xC7, 0x2C),  # headlamp
}
SPRITE = [
    "................",
    ".............w.w",
    "............www.",
    "...........ww...",
    ".ooooo.....dd...",
    ".ooooo.....dd...",
    ".owwwo.....dd...",
    ".owwwo.ooooooo..",
    ".ooooo.ooooooy..",
    ".ooooo.ooooooo..",
    ".ooooo.ooooooo..",
    ".dddddddddddddd.",
    "..kk..kk...kk...",
    "..kk..kk...kk...",
    "gggggggggggggggg",
    "................",
]


def chunk(tag, data):
    body = tag + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))


def main():
    size = len(SPRITE) * SCALE
    raw = b""
    for row in SPRITE:
        scanline = b"".join(
            bytes(PALETTE[ch]) * SCALE for ch in row
        )
        raw += (b"\x00" + scanline) * SCALE  # filter byte 0 per scanline
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
    out = Path(__file__).resolve().parent.parent / "assets" / "avatar.png"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(png)
    print(f"Wrote {out} ({size}x{size})")


if __name__ == "__main__":
    main()
